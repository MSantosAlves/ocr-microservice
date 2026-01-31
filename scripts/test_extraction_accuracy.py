#!/usr/bin/env python3
"""
Script de teste de acurácia do endpoint de extração de OCR.

Testa os arquivos de amostra e compara com resultados esperados.

Usage:
    python scripts/test_extraction_accuracy.py
"""

import json
import sys
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

import requests


# Configuração
API_URL = "http://127.0.0.1:8000/api/v1/ocr/extract"
SAMPLES_DIR = Path(__file__).parent.parent / "samples" / "auto"
ANALYSIS_DIR = Path(__file__).parent.parent / "analysis"
PROMPT_PATH = Path(__file__).parent.parent / "app" / "prompts" / "exam.md"


# Resultados esperados (baseado em expected_results.md)
EXPECTED_RESULTS = {
    "mc_reduced_noise.png": {
        "tipo": "mista",
        "layout": "2 colunas verticais",
        "multipla_escolha": {
            1: "B",
            2: "D",
            3: "C",
            4: "D",
            5: "B",
            6: "A",
        },
        "dissertativas": {}
    },
    "mc_2_reduced_noise.png": {
        "tipo": "mista",
        "layout": "2 colunas verticais",
        "multipla_escolha": {
            1: "A",
            2: "C",
            3: "C",
            4: "D",
            5: "B",
            6: "D",
            7: "A",
        },
        "dissertativas": {}
    },
    "mc_3_reduced_noise.png": {
        "tipo": "mista",
        "layout": "2 colunas verticais",
        "multipla_escolha": {
            1: "A",
            2: "A",
            3: "D",
            4: "B",
            5: "C",
            6: "C",
        },
        "dissertativas": {}
    },
    "prova_mista.jpeg": {
        "tipo": "mista",
        "layout": "2 colunas verticais",
        "multipla_escolha": {
            7: "D",
            8: "A",
            9: "A",
            10: "D",
        },
        "dissertativas": {
            11: "Os sumérios foram os primeiros a construir cidade organizada como [ilegível] e [ilegível]. Nessas cidades, havia ruas, templos, praças e arte [possível: canais]. Para levar água para plantações.",
            12: "Ele consegiu unir varias cidades da Mesopotâmia, criando chamado primeiro imperio Babilônio.",
            13: "Dentro do crescente fertil havia uma parte chamada Mesopotâmia, que significava \"terra entre rios\", porque ficava entre os rios Tigre e Eufrates.",
            14: "Eles usavam [ilégivel] excrito para registro colheita leis, historia e arte poesias, isso mostra como a sociedade deles estavam se tornou complexa, com o comercio, religião, governo e cultura organizada.",
        }
    },
    "prova_mista_2.jpeg": {
        "tipo": "mista",
        "layout": "2 colunas verticais",
        "multipla_escolha": {
            7: "A",
            8: "B",
            9: "B",
            10: "C",
        },
        "dissertativas": {
            11: "A escrita cuneiforme.",
            12: "Porque o codigo de hamurábi eram as leis",
            13: "O rio tigre e eufrates fertilizavam o solo e enrrigava a agricultura",
            14: "A invenção da escrita ajudou a criar leis e também ajudar os comerciantes",
        }
    },
    "prova_mista_3.jpeg": {
        "tipo": "mista",
        "layout": "2 colunas verticais",
        "multipla_escolha": {
            8: "C",
            9: "A",
            10: "C",
        },
        "dissertativas": {
            11: "era feito a  mão eu acho que era mais cara porque era feito a mão por isso era mais [ilegível] [texto riscado] acessar",
            12: "[Em branco]",
            13: "[Em branco]",
            14: "não porque [ilegível] fica tudo mais [ilegível][ilegível] o professor da um ponto a mais [ilegível] [ilegível]",
        }
    },
}


def similarity_ratio(text1: str, text2: str) -> float:
    """Calcula similaridade entre dois textos (0.0 a 1.0)."""
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()


def extract_questoes_from_response(text: str) -> dict:
    """Extrai questões da resposta do OCR."""
    questoes = {
        "multipla_escolha": {},
        "dissertativas": {},
    }
    
    lines = text.strip().split("\n")
    current_questao = None
    current_type = None
    resposta_lines = []
    
    for i, line in enumerate(lines):
        line = line.strip()
        
        # Ignorar linhas de cabeçalho
        if line.startswith("Prova do tipo:") or line.startswith("Layout da prova:"):
            continue
        
        # Detectar número da questão
        if line.startswith("Questão") or line.startswith("Questao"):
            # Salvar questão anterior se existir
            if current_questao and current_type == "dissertativa" and resposta_lines:
                questoes["dissertativas"][current_questao] = " ".join(resposta_lines).strip()
            
            # Nova questão
            resposta_lines = []
            current_type = None
            try:
                # Extrair número da questão
                parts = line.replace("Questão", "").replace("Questao", "").strip().split()
                if parts:
                    current_questao = int(parts[0])
            except:
                continue
                
        elif line.startswith("Alternativa marcada:"):
            # Questão de múltipla escolha
            letra = line.split(":")[-1].strip()
            # Remover "Letra" se presente
            if "Letra" in letra:
                letra = letra.split()[-1]
            if current_questao:
                questoes["multipla_escolha"][current_questao] = letra
                current_type = "multipla"
                
        elif line.startswith("Resposta do aluno:") or line.startswith("Resposta:") or line.startswith("Reposta:"):
            # Questão dissertativa (note: "Reposta" é um typo comum)
            current_type = "dissertativa"
            resposta = line.split(":", 1)[-1].strip()
            if resposta:
                resposta_lines.append(resposta)
                
        elif current_type == "dissertativa" and line and not line.startswith("Questão") and not line.startswith("Questao"):
            # Continuação da resposta (qualquer linha que não seja nova questão)
            if not line.startswith("Prova do tipo:") and not line.startswith("Layout da prova:"):
                resposta_lines.append(line)
    
    # Salvar última questão dissertativa
    if current_questao and current_type == "dissertativa" and resposta_lines:
        questoes["dissertativas"][current_questao] = " ".join(resposta_lines).strip()
    
    return questoes


def test_file(filename: str) -> dict:
    """Testa um arquivo e retorna métricas."""
    file_path = SAMPLES_DIR / filename
    
    if not file_path.exists():
        return {"error": f"Arquivo não encontrado: {file_path}"}
    
    print(f"\n{'='*70}")
    print(f"Testando: {filename}")
    print(f"{'='*70}")
    
    # Fazer requisição
    try:
        with open(file_path, "rb") as f:
            # Detectar tipo de arquivo pelo sufixo
            if filename.endswith('.png'):
                content_type = "image/png"
            else:
                content_type = "image/jpeg"
            
            files = {"file": (filename, f, content_type)}
            data = {
                "document_type": "auto",  # Usar 'auto' para ativar o router
                "language": "pt-BR",
                "preserve_layout": "true",
                "quality_threshold": "0.8",
            }
            response = requests.post(API_URL, files=files, data=data, timeout=120)
        
        if response.status_code != 200:
            print(f"❌ Erro na requisição: {response.status_code}")
            print(response.text)
            return {"error": f"HTTP {response.status_code}"}
        
        result = response.json()
        extracted_text = result.get("text", "")
        
        print(f"\n📄 Texto extraído ({len(extracted_text)} caracteres):")
        print(f"{'-'*70}")
        print(extracted_text)
        print(f"{'-'*70}")
        
    except Exception as e:
        print(f"❌ Erro ao processar arquivo: {e}")
        return {"error": str(e)}
    
    # Comparar com esperado
    expected = EXPECTED_RESULTS.get(filename, {})
    if not expected:
        print(f"⚠️  Sem resultados esperados para este arquivo")
        return {"error": "Sem dados esperados"}
    
    # Extrair questões do texto
    extracted = extract_questoes_from_response(extracted_text)
    
    # Métricas múltipla escolha
    mc_total = len(expected["multipla_escolha"])
    mc_correct = 0
    mc_errors = []
    
    for questao, letra_esperada in expected["multipla_escolha"].items():
        letra_extraida = extracted["multipla_escolha"].get(questao, "AUSENTE")
        if letra_extraida == letra_esperada:
            mc_correct += 1
        else:
            mc_errors.append(f"Q{questao}: esperado={letra_esperada}, extraído={letra_extraida}")
    
    mc_accuracy = (mc_correct / mc_total * 100) if mc_total > 0 else 0
    
    # Métricas dissertativas
    diss_total = len(expected["dissertativas"])
    diss_similarities = []
    diss_details = []
    
    for questao, texto_esperado in expected["dissertativas"].items():
        texto_extraido = extracted["dissertativas"].get(questao, "AUSENTE")
        similarity = similarity_ratio(texto_esperado, texto_extraido)
        diss_similarities.append(similarity)
        
        if similarity < 0.7:
            diss_details.append({
                "questao": questao,
                "similarity": similarity,
                "esperado": texto_esperado[:80] + "...",
                "extraido": texto_extraido[:80] + "...",
            })
    
    diss_avg_similarity = (sum(diss_similarities) / len(diss_similarities) * 100) if diss_similarities else 0
    
    # Imprimir resultados
    print(f"\n📊 RESULTADOS:")
    print(f"\n  Múltipla Escolha:")
    print(f"    ✓ Acurácia: {mc_accuracy:.1f}% ({mc_correct}/{mc_total})")
    if mc_errors:
        print(f"    ❌ Erros:")
        for error in mc_errors:
            print(f"       - {error}")
    
    print(f"\n  Dissertativas:")
    print(f"    📈 Similaridade média: {diss_avg_similarity:.1f}%")
    if diss_details:
        print(f"    ⚠️  Questões com baixa similaridade (<70%):")
        for detail in diss_details:
            print(f"       - Q{detail['questao']}: {detail['similarity']*100:.1f}%")
            print(f"         Esperado: {detail['esperado']}")
            print(f"         Extraído: {detail['extraido']}")
    
    return {
        "filename": filename,
        "mc_accuracy": mc_accuracy,
        "mc_correct": mc_correct,
        "mc_total": mc_total,
        "diss_avg_similarity": diss_avg_similarity,
        "diss_total": diss_total,
        "mc_errors": mc_errors,
        "low_similarity": diss_details,
    }


def main():
    """Executa testes para todos os arquivos."""
    print("\n" + "="*70)
    print("TESTE DE ACURÁCIA - ENDPOINT DE EXTRAÇÃO OCR")
    print("="*70)
    
    # Verificar se API está disponível
    try:
        response = requests.get("http://127.0.0.1:8000/health", timeout=5)
        if response.status_code != 200:
            print("❌ API não está respondendo. Certifique-se que o servidor está rodando.")
            return 1
    except:
        print("❌ Não foi possível conectar à API em http://127.0.0.1:8000")
        print("   Execute: cd ocr-service && python3 -m uvicorn app.main:app --reload --port 8000")
        return 1
    
    # Testar cada arquivo
    results = []
    for filename in EXPECTED_RESULTS.keys():
        result = test_file(filename)
        if "error" not in result:
            results.append(result)
    
    # Resumo geral
    if results:
        print(f"\n{'='*70}")
        print("📊 RESUMO GERAL")
        print(f"{'='*70}")
        
        avg_mc = sum(r["mc_accuracy"] for r in results) / len(results)
        diss_results = [r for r in results if r.get("diss_total", 0) > 0]
        avg_diss = (
            sum(r["diss_avg_similarity"] for r in diss_results) / len(diss_results)
            if diss_results
            else 0
        )
        
        print(f"\n  Arquivos testados: {len(results)}")
        print(f"  Acurácia média (múltipla escolha): {avg_mc:.1f}%")
        print(f"  Similaridade média (dissertativas): {avg_diss:.1f}%")
        
        # Comentários
        print(f"\n💬 COMENTÁRIOS:")
        
        if avg_mc >= 90:
            print(f"  ✅ Múltipla escolha: Excelente performance")
        elif avg_mc >= 70:
            print(f"  ⚠️  Múltipla escolha: Performance aceitável, há margem para melhoria")
        else:
            print(f"  ❌ Múltipla escolha: Performance baixa, revisar detecção de marcações")
        
        if avg_diss >= 80:
            print(f"  ✅ Dissertativas: Excelente transcrição")
        elif avg_diss >= 60:
            print(f"  ⚠️  Dissertativas: Transcrição aceitável, ainda há alucinações")
        else:
            print(f"  ❌ Dissertativas: Muitas diferenças, revisar prompt e processo")
        
        # Problemas comuns
        print(f"\n🔍 PROBLEMAS IDENTIFICADOS:")
        all_errors = []
        for r in results:
            all_errors.extend(r.get("mc_errors", []))
        
        if all_errors:
            print(f"  - {len(all_errors)} erros em múltipla escolha")
        
        low_sim_count = sum(len(r.get("low_similarity", [])) for r in results)
        if low_sim_count > 0:
            print(f"  - {low_sim_count} questões dissertativas com baixa similaridade")
            print(f"    (provavelmente alucinações ou palavras inventadas)")
        
        if not all_errors and low_sim_count == 0:
            print(f"  ✨ Nenhum problema crítico identificado!")

        # Gerar relatório em markdown no formato do relatório base
        ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
        report_date = datetime.now().strftime("%Y-%m-%d")
        report_path = ANALYSIS_DIR / f"test_results_auto_{report_date}.md"

        prompt_content = ""
        if PROMPT_PATH.exists():
            prompt_content = PROMPT_PATH.read_text(encoding="utf-8")

        # Separar resultados MC puro vs provas mistas
        mc_files = [r for r in results if r["filename"].startswith("mc_")]
        mixed_files = [r for r in results if r["filename"].startswith("prova_mista")]

        avg_mc_puro = sum(r["mc_accuracy"] for r in mc_files) / len(mc_files) if mc_files else 0

        report_lines = []
        report_lines.append("# Relatório de Teste de Acurácia - Pasta auto")
        report_lines.append("")
        report_lines.append(f"**Data:** {datetime.now().strftime('%d/%m/%Y')}  ")
        report_lines.append("**Configuração:** `document_type=auto`, pasta `samples/auto`  ")
        report_lines.append("**Objetivo:** Reavaliar acurácia após ajuste do prompt `exam.md`")
        report_lines.append("")
        report_lines.append("## 📊 Resultados Comparativos")
        report_lines.append("")
        report_lines.append("### Múltipla Escolha - Resultados")
        report_lines.append("")
        report_lines.append("| Arquivo | Acurácia MC | Erros |")
        report_lines.append("|---------|-------------|-------|")
        for r in mc_files:
            error_count = len(r.get("mc_errors", []))
            report_lines.append(
                f"| {r['filename']} | **{r['mc_accuracy']:.1f}% ({r['mc_correct']}/{r['mc_total']})** | {error_count} |"
            )
        report_lines.append(f"| **MÉDIA MC PURO** | **{avg_mc_puro:.1f}%** | - |")
        report_lines.append("")
        report_lines.append("### Provas Mistas - Resultados")
        report_lines.append("")
        report_lines.append("| Arquivo | MC Acurácia | Dissertativas | Status |")
        report_lines.append("|---------|-------------|---------------|--------|")
        for r in mixed_files:
            status = "✅" if not r.get("low_similarity") else "⚠️"
            report_lines.append(
                f"| {r['filename']} | **{r['mc_accuracy']:.1f}% ({r['mc_correct']}/{r['mc_total']})** | {r['diss_avg_similarity']:.1f}% | {status} |"
            )
        report_lines.append("")
        report_lines.append("## 🔍 Análise Detalhada")
        report_lines.append("")
        report_lines.append("### ✅ Múltipla Escolha")
        report_lines.append("")
        for r in mc_files:
            report_lines.append(f"**{r['filename']}: {r['mc_accuracy']:.1f}%**")
            if r.get("mc_errors"):
                report_lines.append("- Erros:")
                for err in r["mc_errors"]:
                    report_lines.append(f"  - {err}")
            else:
                report_lines.append("- Sem erros detectados")
            report_lines.append("")
        report_lines.append("### ⚠️ Dissertativas")
        report_lines.append("")
        for r in mixed_files:
            if r.get("low_similarity"):
                report_lines.append(f"**{r['filename']} - Questões com baixa similaridade:**")
                for detail in r["low_similarity"]:
                    report_lines.append(
                        f"- Q{detail['questao']}: {detail['similarity']*100:.1f}%"
                    )
                    report_lines.append(f"  - Esperado: {detail['esperado']}")
                    report_lines.append(f"  - Extraído: {detail['extraido']}")
                report_lines.append("")
        report_lines.append("## 📈 Métricas Consolidadas")
        report_lines.append("")
        report_lines.append("```")
        report_lines.append("Performance atual:")
        report_lines.append(f"├─ Múltipla Escolha (geral): {avg_mc:.1f}%")
        report_lines.append(f"│  └─ MC Puro: {avg_mc_puro:.1f}%")
        report_lines.append(f"└─ Dissertativas: {avg_diss:.1f}%")
        report_lines.append("```")
        report_lines.append("")
        report_lines.append("## 📝 Conclusão")
        report_lines.append("")
        report_lines.append(
            f"Acurácia média de múltipla escolha em **{avg_mc:.1f}%** e similaridade média das dissertativas em **{avg_diss:.1f}%**."
        )
        report_lines.append("")
        report_lines.append("---")
        report_lines.append(f"**Arquivos testados:** {len(results)}  ")
        report_lines.append("**Script:** `scripts/test_extraction_accuracy.py`  ")
        report_lines.append("**Prompt:** `app/prompts/exam.md`")
        report_lines.append("")
        report_lines.append("## Prompt utilizado")
        report_lines.append("")
        report_lines.append("```")
        report_lines.append(prompt_content.strip())
        report_lines.append("```")

        report_path.write_text("\n".join(report_lines).strip() + "\n", encoding="utf-8")
    
    print(f"\n{'='*70}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
