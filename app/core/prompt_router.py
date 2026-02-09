from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import anthropic
from PIL import Image

from app.core.config import get_settings
from app.utils.image_processing import resize_max_side
import logging


class DocumentPromptRouter:
    """
    Router inteligente que classifica documentos manuscritos e seleciona
    o prompt mais adequado para extração de texto.
    
    Categorias suportadas:
    - essay: Redações, textos dissertativos, composições
    - exam: Provas escolares (múltipla escolha e/ou dissertativas)
    - general: Documentos gerais, anotações, cartas
    """
    
    CATEGORIES = ("essay", "exam", "general", "malicious_content", "non_related_content")
    PROMPT_MAP = {
        "essay": "handwritten_essay.md",
        "exam": "exam.md",
        "general": "handwritten_general.md",
    }
    CLASSIFICATION_PROMPT_FILE = "classification_prompt.md"
    
    # Cache de prompts carregados
    _prompt_cache: Dict[str, str] = {}

    def __init__(self) -> None:
        self.settings = get_settings()
        model = self.settings.anthropic_classifier_model or self.settings.anthropic_model
        if not model:
            raise ValueError("ANTHROPIC_CLASSIFIER_MODEL is required for prompt routing.")
        self.model = model
        self.logger = logging.getLogger(__name__)
        self.client = anthropic.Anthropic(
            api_key=self.settings.anthropic_api_key,
            timeout=self.settings.anthropic_timeout_seconds,
        )
        
        # Pré-carregar prompts no cache
        self._preload_prompts()
    
    def _preload_prompts(self) -> None:
        """Carrega todos os prompts no cache durante a inicialização."""
        prompts_dir = Path(__file__).parent.parent / "prompts"
        
        # Carregar prompts de extração
        for prompt_file in self.PROMPT_MAP.values():
            prompt_path = prompts_dir / prompt_file
            if prompt_path.exists():
                self._prompt_cache[prompt_file] = prompt_path.read_text(encoding="utf-8")
                self.logger.debug(f"Prompt carregado no cache: {prompt_file}")
            else:
                self.logger.warning(f"Prompt não encontrado: {prompt_path}")
        
        # Carregar prompt de classificação
        classification_path = prompts_dir / self.CLASSIFICATION_PROMPT_FILE
        if classification_path.exists():
            self._prompt_cache[self.CLASSIFICATION_PROMPT_FILE] = classification_path.read_text(encoding="utf-8")
            self.logger.debug(f"Prompt de classificação carregado no cache: {self.CLASSIFICATION_PROMPT_FILE}")
        else:
            self.logger.warning(f"Prompt de classificação não encontrado: {classification_path}")

    def classify(
        self, 
        image: Image.Image, 
        additional_images: Optional[List[Image.Image]] = None,
        confidence_threshold: float = 0.7
    ) -> Tuple[str, Dict[str, any]]:
        """
        Classifica o documento e retorna o prompt mais adequado.
        
        Args:
            image: Imagem principal para classificação
            additional_images: Imagens adicionais para análise multi-página
            confidence_threshold: Limiar mínimo de confiança (0.0 a 1.0)
            
        Returns:
            Tuple com (nome_do_prompt, metadados_da_classificação)
        """
        classification_prompt = self._build_classification_prompt()
        image_b64 = self._image_to_base64(image)

        last_error: Exception | None = None
        start_time = time.monotonic()
        
        for attempt in range(1, self.settings.anthropic_max_retries + 1):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=256,  # Aumentado para permitir resposta mais detalhada
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": classification_prompt},
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/jpeg",
                                        "data": image_b64,
                                    },
                                },
                            ],
                        }
                    ],
                )
                
                content = "".join(
                    block.text for block in response.content if block.type == "text"
                )
                
                # Extrair métricas de uso
                usage = getattr(response, "usage", None)
                input_tokens = getattr(usage, "input_tokens", None) if usage else None
                output_tokens = getattr(usage, "output_tokens", None) if usage else None
                
                # Parse da resposta com validação de confiança
                category, confidence, reasoning = self._parse_classification_response(content)
                category = self._force_malicious_when_prompt_injection(
                    category=category,
                    raw_response=content,
                    reasoning=reasoning,
                )
                
                # Para categorias bloqueadas, retornar imediatamente sem selecionar prompt.
                if category in {"malicious_content", "non_related_content"}:
                    classification_time_ms = int((time.monotonic() - start_time) * 1000)
                    self.logger.warning(
                        "Documento bloqueado pelo classificador: category=%s, confidence=%.2f",
                        category,
                        confidence,
                    )
                    return "", {
                        "category": category,
                        "confidence": confidence,
                        "reasoning": reasoning,
                        "model": self.model,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "classification_time_ms": classification_time_ms,
                        "attempts": attempt,
                        "is_blocked_category": True,
                    }

                # Para categorias válidas, aplicar threshold e fallback para "general".
                if confidence < confidence_threshold:
                    self.logger.warning(
                        f"Baixa confiança na classificação: {confidence:.2f} < {confidence_threshold}. "
                        f"Usando categoria padrão 'general'."
                    )
                    category = "general"
                    prompt_name = "handwritten_general.md"
                else:
                    prompt_name = self.PROMPT_MAP.get(category, "handwritten_general.md")
                classification_time_ms = int((time.monotonic() - start_time) * 1000)
                
                self.logger.info(
                    f"Documento classificado: category={category}, confidence={confidence:.2f}, "
                    f"prompt={prompt_name}, model={self.model}, time={classification_time_ms}ms"
                )
                
                return prompt_name, {
                    "category": category,
                    "confidence": confidence,
                    "reasoning": reasoning,
                    "model": self.model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "classification_time_ms": classification_time_ms,
                    "attempts": attempt,
                }
                
            except Exception as error:
                last_error = error
                self.logger.warning(
                    f"Tentativa {attempt}/{self.settings.anthropic_max_retries} falhou: {error}"
                )
                if attempt < self.settings.anthropic_max_retries:
                    backoff_seconds = 2 ** attempt
                    self.logger.debug(f"Aguardando {backoff_seconds}s antes de retentar...")
                    time.sleep(backoff_seconds)

        # Se todas as tentativas falharem, usar fallback
        self.logger.error(f"Todas as tentativas de classificação falharam: {last_error}")
        return self._get_fallback_prompt(last_error)

    def _force_malicious_when_prompt_injection(
        self,
        category: str,
        raw_response: str,
        reasoning: str,
    ) -> str:
        """
        Override defensivo para reduzir falso-negativo de conteúdo malicioso.
        Se houver sinais claros de prompt injection/manipulação, forçar malicious_content.
        """
        if category == "malicious_content":
            return category

        combined = f"{raw_response} {reasoning}".lower()
        suspicious_patterns = (
            "chave de api",
            "api key",
            "token de api",
            "prompt injection",
            "engenharia de prompt",
            "ignore as instruções",
            "ignore previous instructions",
            "burlar regras",
            "bypass",
            "jailbreak",
            "system prompt",
        )

        if any(pattern in combined for pattern in suspicious_patterns):
            self.logger.warning(
                "Reclassificando para malicious_content por sinal de prompt injection."
            )
            return "malicious_content"

        return category

    def _build_classification_prompt(self) -> str:
        """Carrega o prompt de classificação do cache ou arquivo .md."""
        # Tentar carregar do cache primeiro
        if self.CLASSIFICATION_PROMPT_FILE in self._prompt_cache:
            return self._prompt_cache[self.CLASSIFICATION_PROMPT_FILE]
        
        # Se não estiver no cache, carregar do arquivo
        prompts_dir = Path(__file__).parent.parent / "prompts"
        prompt_path = prompts_dir / self.CLASSIFICATION_PROMPT_FILE
        
        if not prompt_path.exists():
            raise FileNotFoundError(f"Classification prompt file not found: {prompt_path}")
        
        prompt_content = prompt_path.read_text(encoding="utf-8")
        self._prompt_cache[self.CLASSIFICATION_PROMPT_FILE] = prompt_content
        return prompt_content

    def _parse_classification_response(self, content: str) -> Tuple[str, float, str]:
        """
        Parse da resposta de classificação com extração de confiança e raciocínio.
        
        Returns:
            Tuple com (categoria, confiança, raciocínio)
        """
        try:
            # Tentar extrair JSON da resposta
            json_match = re.search(r'\{[^}]+\}', content, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(0))
            else:
                parsed = json.loads(content)
            
            category = str(parsed.get("category", "")).lower().strip()
            confidence = float(parsed.get("confidence", 0.5))
            reasoning = str(parsed.get("reasoning", ""))
            
            # Validar categoria
            if category not in self.CATEGORIES:
                self.logger.warning(f"Categoria inválida retornada: {category}")
                category = self._extract_category_from_text(content)
                confidence = max(0.3, confidence - 0.2)  # Reduzir confiança
            
            # Validar confiança
            confidence = max(0.0, min(1.0, confidence))
            
            return category, confidence, reasoning
            
        except (json.JSONDecodeError, ValueError, KeyError) as error:
            self.logger.warning(f"Erro ao parsear resposta JSON: {error}. Tentando extração por regex.")
            category = self._extract_category_from_text(content)
            return category, 0.5, "Classificação extraída por fallback"
    
    def _extract_category_from_text(self, content: str) -> str:
        """Extrai categoria do texto usando regex como fallback."""
        match = re.search(
            r"\b(essay|exam|general|malicious_content|non_related_content)\b",
            content.lower(),
        )
        if match:
            return match.group(1)
        return "general"
    
    def _get_fallback_prompt(self, error: Exception) -> Tuple[str, Dict[str, any]]:
        """Retorna prompt padrão quando a classificação falha completamente."""
        self.logger.error(f"Usando prompt fallback devido a erro: {error}")
        return "handwritten_general.md", {
            "category": "general",
            "confidence": 0.0,
            "reasoning": "Fallback devido a falha na classificação",
            "model": self.model,
            "input_tokens": 0,
            "output_tokens": 0,
            "classification_time_ms": 0,
            "error": str(error),
            "is_fallback": True,
        }

    def classify_multipage(
        self, 
        images: List[Image.Image], 
        sample_size: int = 3
    ) -> Tuple[str, Dict[str, any]]:
        """
        Classifica documento com múltiplas páginas analisando uma amostra.
        
        Args:
            images: Lista de imagens do documento
            sample_size: Número de páginas a analisar (padrão: 3)
            
        Returns:
            Tuple com (nome_do_prompt, metadados_da_classificação)
        """
        if not images:
            return self._get_fallback_prompt(ValueError("Lista de imagens vazia"))
        
        # Se houver apenas uma imagem, usar classificação simples
        if len(images) == 1:
            return self.classify(images[0])
        
        # Analisar amostra de páginas (primeira, meio, última)
        sample_indices = self._get_sample_indices(len(images), sample_size)
        sampled_images = [images[i] for i in sample_indices]
        
        self.logger.info(
            f"Classificação multi-página: {len(images)} páginas, "
            f"analisando páginas {sample_indices}"
        )
        
        # Classificar primeira página (mais representativa)
        return self.classify(sampled_images[0], additional_images=sampled_images[1:])
    
    def _get_sample_indices(self, total_pages: int, sample_size: int) -> List[int]:
        """
        Retorna índices de páginas para amostragem inteligente.
        Prioriza: primeira página, página do meio, última página.
        """
        if total_pages <= sample_size:
            return list(range(total_pages))
        
        indices = [0]  # Sempre incluir primeira página
        
        if sample_size > 1:
            indices.append(total_pages - 1)  # Última página
        
        if sample_size > 2:
            middle = total_pages // 2
            indices.insert(1, middle)  # Página do meio
        
        # Adicionar páginas adicionais se necessário
        remaining = sample_size - len(indices)
        if remaining > 0:
            step = total_pages // (remaining + 1)
            for i in range(1, remaining + 1):
                idx = step * i
                if idx not in indices and idx < total_pages:
                    indices.append(idx)
        
        return sorted(indices)
    
    def get_prompt_content(self, prompt_name: str) -> Optional[str]:
        """
        Retorna o conteúdo de um prompt do cache.
        
        Args:
            prompt_name: Nome do arquivo de prompt
            
        Returns:
            Conteúdo do prompt ou None se não encontrado
        """
        return self._prompt_cache.get(prompt_name)
    
    def get_available_categories(self) -> List[Dict[str, str]]:
        """
        Retorna lista de categorias disponíveis com suas descrições.
        
        Returns:
            Lista de dicionários com informações das categorias
        """
        return [
            {
                "category": "malicious_content",
                "prompt_file": "none",
                "description": "Conteúdo malicioso/proibido; documento deve ser bloqueado",
            },
            {
                "category": "non_related_content",
                "prompt_file": "none",
                "description": "Conteúdo fora do contexto educacional",
            },
            {
                "category": "essay",
                "prompt_file": "handwritten_essay.md",
                "description": "Redações, textos dissertativos, composições",
            },
            {
                "category": "exam",
                "prompt_file": "exam.md",
                "description": "Provas escolares (múltipla escolha e/ou dissertativas)",
            },
            {
                "category": "general",
                "prompt_file": "handwritten_general.md",
                "description": "Documentos gerais, anotações, cartas",
            },
        ]

    @staticmethod
    def _image_to_base64(image: Image.Image, max_size: int = 2000) -> str:
        """
        Converte imagem para base64 otimizando tamanho e qualidade.
        
        Args:
            image: Imagem PIL a ser convertida
            max_size: Tamanho máximo do lado maior em pixels
            
        Returns:
            String base64 da imagem
        """
        from io import BytesIO

        max_bytes = 5 * 1024 * 1024  # 5MB limite da API
        current = image.convert("RGB")
        max_side = max_size
        quality = 85

        # Tentar comprimir progressivamente até atingir o tamanho desejado
        for iteration in range(6):
            resized = resize_max_side(current, max_side)
            with BytesIO() as stream:
                resized.save(stream, format="JPEG", quality=quality, optimize=True)
                data = stream.getvalue()
            
            if len(data) <= max_bytes:
                return base64.b64encode(data).decode("ascii")

            # Reduzir tamanho e qualidade progressivamente
            max_side = int(max_side * 0.8)
            quality = max(50, quality - 10)

        # Última tentativa com qualidade mínima
        with BytesIO() as stream:
            resized = resize_max_side(current, max_side)
            resized.save(stream, format="JPEG", quality=50, optimize=True)
            return base64.b64encode(stream.getvalue()).decode("ascii")
