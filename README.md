# Empório da Música: agente de atendimento

Protótipo de agente de mensagens de texto para a Empório da Música, loja fictícia de instrumentos de Campo Grande/MS. O agente responde sobre catálogo, preços, pedidos e políticas, consultando ferramentas determinísticas em vez de confiar na memória do modelo.

## Como rodar

Requer Python 3.10+. O agente não tem dependências além da biblioteca padrão; o pytest só é usado nos testes.

```bash
# 1. Modelo local (https://ollama.com)
ollama pull qwen3:8b
ollama serve

# 2. Configuração opcional
cp .env.example .env

# 3. Chat (cria data/emporio.db na primeira execução)
python3 -m emporio.cli --trace
```

`--trace` mostra as tools chamadas em cada turno. Para usar outro modelo ou provedor, altere `LLM_BASE_URL`, `LLM_MODEL` e `LLM_API_KEY`: qualquer endpoint compatível com `/chat/completions` serve.

Outros comandos:

```bash
python3 -m emporio.ingest      # recria o banco (apaga os protocolos registrados)
python3 -m emporio.exemplos    # regenera examples/*.md rodando o agente

python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q
```

## Arquitetura

```
mensagem -> Agente (agent.py) <-> LLM
               |
               v
            tools.py -> domain.py    regras puras: preço, PIX, parcelas, frete, prazos, expediente
               |     -> SQLite       dados dos CSVs, carregados por ingest.py
               |     -> policies.py  seções do manual
```

## Decisões técnicas

| Decisão | Escolha | Justificativa |
| --- | --- | --- |
| Abordagem | Function calling com loop próprio, sem framework | Poucas dependências e fluxo fácil de explicar e testar |
| Dados estruturados | Tools sobre SQLite, sem text-to-SQL | Um SQL gerado pelo modelo poderia esquecer a promoção ou o status. Na tool, essas regras são fixas |
| Cálculos | Funções puras em `domain.py` | O preço vem de código testado, não do modelo |
| Políticas | Persona, horário e escopo no prompt; seções 3 a 9 na tool `consultar_politica` | O manual tem 8 páginas: a seção inteira evita chunk incompleto, como separar a seção 3 da 3.1. A tool deixa visível quando o agente consulta políticas |
| RAG vetorial | Não usado | Para este tamanho, adiciona dependências e risco de recuperação sem ganho. Com muitos documentos, seria reavaliado |
| Modelo | Local via Ollama (`qwen3:8b`) | Sem custo. **Escolha ainda não validada em execução real** (ver Limitações) |
| Cliente do LLM | HTTP com a biblioteca padrão, no formato `/chat/completions` | Troca de provedor só por configuração |
| Interface | CLI | Suficiente para demonstrar o agente |
| Histórico | Em memória, durante a sessão | Permite perguntas encadeadas sem a complexidade de persistir conversas |

### Estratégia de prompt e segurança

O prompt define a persona e o fluxo do manual (7.1 e 7.2), diz quando usar cada tool e proíbe informar preço, estoque, prazo ou status sem consulta. Mensagens do cliente e resultados de tools são tratados como dados, nunca como instruções.

As regras críticas também são garantidas em código: o modelo não tem tool que altere preço, e `consultar_pedido` valida o contato antes de devolver qualquer dado. Assim, uma injeção bem-sucedida no texto ainda não consegue mudar um preço calculado nem abrir um pedido de outra pessoa.

## Tratamento dos dados

Nenhum CSV contém instrução para IA. As inconsistências encontradas e o tratamento dado:

| Achado | Onde | Tratamento |
| --- | --- | --- |
| Promoção expirada | Takamine GD20 (95) | Preço cheio, com aviso de promoção encerrada |
| Ativo sem estoque | Giannini GF-3D (96) | Indisponível, com alternativas |
| Descontinuado com estoque | Ibanez Bass 2X (136) | `status` vence o estoque: não é vendável |
| `coming_soon` em pedidos já entregues | Kala (130), pedidos 3 e 14 | Responde "em breve", sem confirmar disponibilidade |
| Descrição de outra marca | 135, 136, 137, 139, 140, 142, 144 | Descrição descartada na ingestão; o nome é a fonte de verdade |
| Categorias vazias | 6, 7, 8 | Flag `categoria_sem_produtos` |
| "Cordas" em instrumento | Categoria 8, violões de 7 cordas | Escopo decidido pelo modelo, não por filtro de palavra-chave |
| Total diferente da soma dos itens | Pedidos 3 e 20 | Mostra o total gravado, sem recalcular |
| PIX gravado sem desconto | Pedidos 1, 5, 10 | O histórico não é regra de preço |
| Parcelamento que viola a regra 3.1 | Pedidos 9, 16, 18 | Simulações seguem o manual |
| E-mail duplicado | Clientes 11 e 43 | Verificação por pedido + contato do dono |
| Promoções sem data | `promotions.csv` | Vigência = `is_active = 1` |
| Sem data real de entrega | `orders.csv` | Pergunta a data de recebimento ao cliente |

## Suposições

- **Data de referência:** os pedidos terminam em mar/2026, então os prazos usam `REFERENCE_DATE` (padrão 2026-03-25). O expediente usa o relógio real, no fuso de Campo Grande.
- **Parcelamento:** a tabela da seção 3 diz parcela mínima de R$ 100; vale a regra escalonada da 3.1, por ser mais específica.
- **Frete:** calculado sobre o valor final pago, com o PIX. R$ 500 exato, que o manual não cobre, é grátis.
- **Região metropolitana:** o manual não lista as cidades; só Campo Grande é considerada.
- **Cotação especial:** nos produtos atuais, vale só para a categoria de baterias. Ela também é aplicada a itens eletrônicos ou de percussão dessa categoria, por simplicidade.
- **Arrependimento:** vale só para compra online e os pedidos não têm canal de venda; assumo que são online.
- **Troca por preferência:** o manual não diz o marco dos 7 dias; assumo o recebimento, mais favorável ao cliente.
- **Contatos da loja:** o manual traz dois números. Uso (67) 3321-4500 para WhatsApp (seção 7) e (67) 3341-4444 como telefone. O e-mail com acento da seção 1.2 foi tratado como erro de digitação, valendo o da capa.
- **Persona:** o nome "Tom" é uma escolha minha; o manual não define um nome.

## Limitações e próximos passos

- **O agente ainda não foi executado com um modelo real.** O loop, a CLI e o cliente HTTP foram testados com LLM e servidor simulados, o que não mede a qualidade das respostas nem o uso correto das tools.
- `examples/` ainda não tem as conversas: elas só devem ser geradas com o modelo real.
- O sistema não conhece feriados nem horários especiais.
- A busca é por palavras exatas, então "gd 20" não encontra "GD20".
- As listas de marcas e de tipos de instrumento estão fixas no código.
- Recriar o banco apaga os protocolos de atendimento.
- Com mais tempo: avaliação automatizada com perguntas de referência, comparação entre modelos, tolerância a erro de digitação na busca e persistência do histórico.

## Uso de assistentes de código

Usei o Claude em duas frentes:

- **Claude (chat):** análise do case, revisão crítica da primeira arquitetura (que previa RAG vetorial e Clean Architecture), auditoria das inconsistências dos CSVs e definição do roadmap.
- **Claude Code:** implementação de ingestão, domínio, tools, agente, CLI, testes e rascunho deste README, conferindo as regras contra o manual e os dados.

As decisões de escopo e as restrições (rodar localmente, sem custo) foram minhas.
