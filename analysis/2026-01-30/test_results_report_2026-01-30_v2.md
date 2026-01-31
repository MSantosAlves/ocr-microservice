# Relatório de Teste de Acurácia - Extração OCR (v2)

**Data:** 30/01/2026  
**Configuração:** `document_type=mixed` (usa router + prompt exam)  
**Arquivos testados:** 6 (3 apenas MC + 3 mistos)

## 📊 Resultados Detalhados

### Provas Apenas Múltipla Escolha

| Arquivo | Total Questões | Acertos | Acurácia | Problemas |
|---------|----------------|---------|----------|-----------|
| mc.jpeg | 6 | 5 | **83.3%** | Q5: B→A |
| mc_2.jpeg | 7 | 3 | **42.9%** | Q1: A→B, Q3: C→"em branco", Q5: B→D, Q6: D→B |
| mc_3.jpeg | 6 | 3 | **50.0%** | Q1: A→B, Q3: D→C, Q4: B→D |
| **MÉDIA MC PURO** | | | **58.7%** | **❌ Performance baixa** |

### Provas Mistas (MC + Dissertativas)

| Arquivo | MC Acurácia | Dissertativas Similaridade | Status |
|---------|-------------|---------------------------|--------|
| prova_mista.jpeg | **100%** (4/4) | **73.5%** | ⚠️ Alucinações em Q11,Q12 |
| prova_mista_2.jpeg | **100%** (4/4) | **81.5%** | ⚠️ Alucinação em Q13 |
| prova_mista_3.jpeg | **100%** (3/3) | **81.8%** | ⚠️ Q14 diferente |
| **MÉDIA MC MISTO** | **100%** | **78.9%** | ✅ |

## 🔍 Análise por Categoria

### 1. Múltipla Escolha em Provas Puras: ❌ Problemático (58.7%)

**Problemas identificados:**

**mc_2.jpeg (42.9% - pior resultado):**
- Q1: Marcação não detectada corretamente
- Q3: Detectou "em branco" quando estava marcado C
- Q5 e Q6: Inversões de letras

**mc_3.jpeg (50.0%):**
- 3 erros em 6 questões
- Padrão: letras consecutivas confundidas (A/B, C/D)

**Possíveis causas:**
- Qualidade de marcação mais fraca
- Layout diferente das provas mistas
- Modelo pode estar "esperando" dissertativas também

### 2. Múltipla Escolha em Provas Mistas: ✅ Excelente (100%)

**Todos os 3 arquivos: 100% acurácia!**
- Total: 11/11 questões corretas
- Nenhum erro de detecção
- Formato funciona perfeitamente

### 3. Dissertativas: ⚠️ Bom mas com alucinações (78.9%)

**Sucessos:**
- ✅ Estrutura mantida corretamente
- ✅ Detecção de "em branco" (prova_mista_3 Q12, Q13)
- ✅ Mantém erros de ortografia ("dificil", "hamurabi")

**Problemas recorrentes:**

**Q11 (prova_mista.jpeg) - 55% similaridade:**
```
Esperado: "Os sumérios foram os primeiros a construir cidade organizada 
          como [ilegível] e [ilegível]..."
          
Extraído: "Os sumerios foram os primeiros povos a criar cidades, 
          agricultura e leis (códigos)..."
```
❌ Inventou: "povos", "agricultura", "leis (códigos)"

**Q12 (prova_mista.jpeg) - 62.3% similaridade:**
```
Esperado: "Ele consegiu unir varias cidades..."

Extraído: "quando se fala dos babilônios ele construiu um varias cidades..."
```
❌ Inventou: "quando se fala dos babilônios", "construiu"

**Q13 (prova_mista_2.jpeg) - 65.2% similaridade:**
```
Esperado: "O rio tigre e eufrates fertilizavam o solo..."

Extraído: "O que irrig e enrigação utilizavam a roda..."
```
❌ Leitura completamente errada, parece ter confundido palavras

**Q14 (prova_mista_3.jpeg) - 61.5% similaridade:**
```
Esperado: "não porque [ilegível]..."

Extraído: "Sim porque hoje fica tudo mais facc[o/í]a..."
```
❌ Inverteu "não" → "Sim", inventou palavras

## 💬 Comentários e Observações

### ✅ Pontos Fortes
1. **MC em provas mistas: perfeito** - 100% nos 3 arquivos
2. **Estrutura respeitada** - Formato sempre correto
3. **Detecção de branco** - Identifica respostas não preenchidas
4. **Erros preservados** - Mantém ortografia original

### ❌ Pontos Fracos
1. **MC em provas puras: ruim** - Apenas 58.7%
2. **Alucinações persistem** - Ainda inventa palavras baseado em contexto
3. **Leituras erradas** - Q13 de prova_mista_2 foi completamente mal lida

### 🤔 Hipóteses

**Por que MC puro tem performance pior?**
1. Layout pode ser diferente (sem espaço para dissertativas)
2. Qualidade das marcações pode ser inferior
3. Modelo pode estar "confuso" sem dissertativas

**Por que MC em misto funciona 100%?**
1. Prompt de "exam" parece otimizado para layout misto
2. Presença de dissertativas ajuda modelo a entender contexto

## 🎯 Recomendações

### Curto Prazo
1. **Investigar arquivos MC puros:**
   - Verificar qualidade de imagem
   - Comparar layout com provas mistas
   - Testar com prompt diferente (não exam)

2. **Ajustar prompt para coibir alucinações:**
   - Reforçar mais a proibição de completar palavras
   - Adicionar exemplos negativos mais explícitos
   - Considerar penalização no sistema de prompts

### Médio Prazo
1. **Criar prompt específico para MC puro:**
   - Foco apenas em detecção de marcações
   - Sem expectativa de dissertativas

2. **Implementar pós-processamento:**
   - Detector de alucinações (palavras históricas comuns)
   - Validação de coerência entre pergunta e resposta

3. **Feedback loop:**
   - Coletar casos reais de alucinações
   - Ajustar prompts baseado em exemplos reais

## 📈 Métricas Consolidadas

```
Performance Geral:
├─ Múltipla Escolha (geral): 79.4%
│  ├─ MC Puro: 58.7% ❌
│  └─ MC Misto: 100% ✅
│
└─ Dissertativas: 78.9% ⚠️
   ├─ Estrutura: 100% ✅
   ├─ Conteúdo: ~79% ⚠️
   └─ Alucinações: ~21% ❌
```

## 🚦 Status para Produção

| Tipo de Prova | Status | Recomendação |
|---------------|--------|--------------|
| Provas Mistas | 🟢 Pronto | Pode usar em produção com monitoramento |
| MC Puro | 🔴 Não pronto | Necessita investigação e correção |
| Dissertativas | 🟡 Quase | Monitorar alucinações, ok para beta |

## 📝 Conclusão

O sistema funciona **excelente para provas mistas** (formato mais comum), mas tem **problemas com provas apenas de múltipla escolha**. 

**Dissertativas** têm boa qualidade (~79%) mas ainda sofrem com alucinações pontuais onde o modelo completa palavras ilegíveis usando conhecimento contextual em vez de marcar `[ilegível]`.

**Ação prioritária:** Investigar por que MC puro tem performance tão inferior ao MC em provas mistas.

---
**Script:** `scripts/test_extraction_accuracy.py`  
**Prompt:** `app/prompts/handwritten_exam.md`
