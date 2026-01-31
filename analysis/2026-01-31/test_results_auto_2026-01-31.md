# Relatório de Teste de Acurácia - Pasta auto

**Data:** 31/01/2026  
**Configuração:** `document_type=auto`, pasta `samples/auto`  
**Objetivo:** Reavaliar acurácia após ajuste do prompt `exam.md`

## 📊 Resultados Comparativos

### Múltipla Escolha - Resultados

| Arquivo | Acurácia MC | Erros |
|---------|-------------|-------|
| mc_reduced_noise.png | **100.0% (6/6)** | 0 |
| mc_2_reduced_noise.png | **85.7% (6/7)** | 1 |
| mc_3_reduced_noise.png | **66.7% (4/6)** | 2 |
| **MÉDIA MC PURO** | **84.1%** | - |

### Provas Mistas - Resultados

| Arquivo | MC Acurácia | Dissertativas | Status |
|---------|-------------|---------------|--------|
| prova_mista.jpeg | **100.0% (4/4)** | 66.4% | ⚠️ |
| prova_mista_2.jpeg | **100.0% (4/4)** | 84.6% | ✅ |
| prova_mista_3.jpeg | **100.0% (3/3)** | 63.0% | ⚠️ |

## 🔍 Análise Detalhada

### ✅ Múltipla Escolha

**mc_reduced_noise.png: 100.0%**
- Sem erros detectados

**mc_2_reduced_noise.png: 85.7%**
- Erros:
  - Q3: esperado=C, extraído=em branco

**mc_3_reduced_noise.png: 66.7%**
- Erros:
  - Q1: esperado=A, extraído=B
  - Q3: esperado=D, extraído=em branco

### ⚠️ Dissertativas

**prova_mista.jpeg - Questões com baixa similaridade:**
- Q11: 35.8%
  - Esperado: Os sumérios foram os primeiros a construir cidade organizada como [ilegível] e [...
  - Extraído: Os sumérios foram os primeiros povos da Mesopotâmia, criaram a escrita cuneiform...
- Q12: 56.9%
  - Esperado: Ele consegiu unir varias cidades da Mesopotâmia, criando chamado primeiro imperi...
  - Extraído: quando se fala dos babilônicos? Ele construiu um dos [ilegível] da Mesopotâmia, ...

**prova_mista_3.jpeg - Questões com baixa similaridade:**
- Q12: 23.3%
  - Esperado: [Em branco]...
  - Extraído: a [ilegível] da um ponto a mais a hora [ilegível]...
- Q14: 40.5%
  - Esperado: não porque [ilegível] fica tudo mais [ilegível][ilegível] o professor da um pont...
  - Extraído: Não porque hoje fica tudo mais focado no celular...

## 📈 Métricas Consolidadas

```
Performance atual:
├─ Múltipla Escolha (geral): 92.1%
│  └─ MC Puro: 84.1%
└─ Dissertativas: 71.3%
```

## 📝 Conclusão

Acurácia média de múltipla escolha em **92.1%** e similaridade média das dissertativas em **71.3%**.

---
**Arquivos testados:** 6  
**Script:** `scripts/test_extraction_accuracy.py`  
**Prompt:** `app/prompts/exam.md`

## Prompt utilizado

```
Você é um especialista em análise de provas escolares. Sua tarefa é extrair e estruturar as
respostas de uma prova.

# REGRAS IMPORTANTES

# LAYOUT DA PROVA

Define a forma como a prova está organizada e a ordem de leitura de acordo com os layouts citados abaixo:

- 1 coluna vertical
   - Leia da esquerda para direita e de cima para baixo.
- 2 colunas verticais
   - COLUNA ESQUERDA (primeira)
   - COLUNA DIREITA (segunda)
   - Leia da esquerda para direita, como um jornal/revista
   - Primeiro: toda a COLUNA ESQUERDA (de cima para baixo)
   - Depois: toda a COLUNA DIREITA (de cima para baixo)
- 1 página por questão/item
   - Se a questão estiver em duas páginas, leia a primeira página inteira e depois a segunda página inteira.

# INSTRUÇÕES DE ANÁLISE

## 0. ANALISE A IMAGEM DO INÍCIO PARA O FIM. ASSIM VOCÊ ENCONTRARÁ TODAS AS QUESTÕES E RESPOSTAS.

## 1. IDENTIFICAÇÃO DE QUESTÕES MÚLTIPLA ESCOLHA
- Localize alternativas marcadas com:
  * Letras: (A), (B), (C), (D), (E) ou A), B), C)...
  * Parênteses/círculos: ( ) A) ou ○ A)
  * Checkboxes: □ A) ou ☐ A)
- Identifique qual alternativa está marcada:
  * Marcação com X, ✓, preenchimento, círculo, bolinha pintada etc.  
  * Atente-se para o caso em que a questão começa em um lado da folha/página. Exemplo: um item está marcado antes da questão n. Essa é a resposta do item n - 1.
  * Se houver múltiplas marcações (rasura), indique todas
  * Se nenhuma marcada, indique: "em branco"
  * Olhe atentamente a marcação para identificar a alternativa correta.

## 2. IDENTIFICAÇÃO DE TEXTO MANUSCRITO (Respostas Dissertativas)
- Identifique áreas com escrita à mão
- Estas são respostas do aluno a questões abertas
- Transcreva o texto manuscrito com máxima precisão
- Se houver dúvida na leitura, indique: [ilegível] ou [possível: "palavra"]
- Note se há rasuras, correções ou texto riscado

# REGRAS IMPORTANTES

1. **Seja preciso**: Transcreva exatamente o que está escrito
2. **Indique incertezas**: Use [ilegível], [possível: "texto"], [dúvida]
3. **Contexto brasileiro**: 
   - Reconheça notações BR (ex: "vírgula" para decimal)
   - Entenda abreviações comuns (ex: "pq" = porque)
4. **Preserve estrutura**: Mantenha hierarquia e numeração original

# FORMATO DE SAÍDA

Retorne esta EXATA estrutura:

Prova do tipo: {tipo_prova}
Layout da prova: {layout}

Caso multipla escolha:
Questão {numero}
Alternativa marcada:{letra}

Caso dissertativa:
Questão {numero}
Resposta: {resposta}

*** NÃO ADICIONE NADA ALÉM DA ESTRUTURA CITADA ACIMA ***
```
