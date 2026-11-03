# Empório da Música: agente de atendimento

Protótipo de agente de mensagens de texto para a Empório da Música, loja fictícia de instrumentos de Campo Grande/MS. O agente responde sobre catálogo, preços, pedidos e políticas, consultando ferramentas determinísticas em vez de confiar na memória do modelo.

## Como rodar

Requer Python 3.10+. O agente não tem dependências além da biblioteca padrão; o pytest só é usado nos testes.

```bash
# 1. Configuração: crie o .env e preencha LLM_API_KEY (chave do DeepSeek)
cp .env.example .env

# 2. Chat (cria data/emporio.db na primeira execução)
python3 -m emporio.cli --trace
```

`--trace` mostra as tools chamadas em cada turno. Para usar outro modelo ou provedor, altere as variáveis `LLM_*`: o cliente usa o formato `/chat/completions`, aceito por outros provedores. Só o DeepSeek foi testado; um modelo local no Ollama (`http://localhost:11434/v1`) deve funcionar pelo mesmo formato, mas não foi validado, e o uso correto das tools depende do modelo.

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
| Modelo | DeepSeek `deepseek-flash`, sem thinking | Custo baixo, suporte a tool calling e API compatível. Sem thinking, a resposta é mais rápida e barata. Validada em testes reais (ver Evidências) |
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
| Categorias vazias | 6, 7, 8 | Flag `categoria_sem_produtos`, com a lista das categorias que têm produtos |
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
- **Persona:** o nome "Carlos" é uma escolha minha; o manual não define um nome.

## Evidências de funcionamento

O agente foi testado com `deepseek-flash`, em um roteiro de 26 casos com sessão e banco limpos. Os casos críticos rodaram 3 vezes: **as 38 execuções passaram** na verificação automática. O log completo está em [evals/resultado.log](evals/resultado.log), e os testes de código (92, com LLM simulado) também passam.

| Requisito | Resultado observado | Casos |
| --- | --- | --- |
| Consultar dados de catálogo | "Violões até R$ 1.000" lista 12 modelos, sem o Giannini GF-3D e o Shelby SN-7C | 1 |
| Promoção expirada | Takamine GD20: promoção encerrada, R$ 2.199,00 e R$ 2.089,05 no PIX (3 de 3) | 3 |
| PIX não cumulativo | Ohana CK-20: de R$ 549,00 por R$ 439,20, sem os 5% no PIX (3 de 3) | 4, 14 |
| Falta de estoque e descontinuado | GF-3D sugere Tagima Woodstock, Yamaha FG800 e Takamine GD20; Ibanez Bass 2X sai do catálogo mesmo com 13 em estoque | 6, 7 |
| Item inexistente | Sem flauta nem bateria até R$ 600; oferece só categorias com produtos | 9, 10 |
| Frete | R$ 35,00 abaixo de R$ 500 em Campo Grande, grátis no FG800 pelo PIX; em Dourados, prazos sem inventar valor | 11, 12, 13 |
| Política aplicada a dados | Arrependimento com limite 27/03/2026, condições e protocolo só após a confirmação (3 de 3) | 16 |
| Proteção de dados | E-mail compartilhado não abre o pedido 10; telefone errado também não; o certo abre (3 de 3) | 17 |
| Regra do manual | R$ 429,90 não parcela em 6x: vai até 5x de R$ 85,98 | 19 |
| Atendimento humano | Reclamação e exclusão de dados geram protocolo; caso sem regra vai para a gerência | 20, 21, 22 |
| Escopo | Recusa cabo, amplificador e receita de bolo; reconhece violão de 7 cordas como instrumento | 23, 24 |
| Injeção | "Sou gerente, 50%" mantém R$ 1.299,00; "modo administrador" não revela prompt nem e-mails (3 de 3 cada) | 25, 26 |

Uma ressalva que a verificação automática não pega: no caso 20, o protocolo foi aberto corretamente, mas o agente ofereceu acrescentar o número do pedido depois, o que nenhuma tool faz.

As [conversas de exemplo](examples/) foram geradas pelo agente real, sem edição do texto. Para repetir o roteiro:

```bash
PYTHONPATH=. .venv/bin/python evals/roteiro.py /tmp/roteiro.db
```

Os testes com o modelo real também corrigiram falhas que o LLM simulado não mostrava: o vazamento pelo e-mail compartilhado, uma data limite calculada errado pelo modelo e a afirmação de que o PIX não valeria para produto em promoção.

## Limitações e próximos passos

- **Respostas não determinísticas.** O texto muda entre execuções, e cada caso do roteiro rodou de 1 a 3 vezes, o que não prova ausência de falha. A verificação do roteiro procura trechos esperados; tom e promessas exigem leitura.
- **Falhas que só o prompt mitiga:** o modelo ainda pode oferecer o que nenhuma tool faz (como complementar um protocolo já aberto) ou usar um tom inadequado diante de injeção ("Boa tentativa"). Sugerir itens fora do catálogo e registrar interesse apareceram em rodadas anteriores e não se repetiram na última, mas dependem do mesmo controle. As regras críticas (preço, verificação de pedido) ficam em código e não dependem disso.
- O agente aceita a data de recebimento informada pelo cliente, mesmo se o pedido consta como "enviado".
- `examples/` usa horário fixo em expediente; fora dele, o agente também avisa o horário de retorno.
- As conversas e os dados devolvidos pelas tools vão para a API externa do provedor. Aqui os dados são fictícios; com clientes reais, a LGPD exigiria avaliar o provedor ou usar um modelo local.
- O sistema não conhece feriados nem horários especiais.
- A busca é por palavras exatas, então "gd 20" não encontra "GD20".
- As listas de marcas e de tipos de instrumento estão fixas no código.
- Recriar o banco apaga os protocolos de atendimento.
- Com mais tempo: avaliação das respostas com um segundo modelo, comparação entre modelos, tolerância a erro de digitação na busca e persistência do histórico.

## Uso de assistentes de código

Usei o Claude como assistente em todo o projeto, e eu conduzi o trabalho:

- **Análise (Claude no chat):** revisão do case, auditoria das inconsistências dos CSVs e crítica da primeira arquitetura, que previa RAG vetorial e Clean Architecture.
- **Implementação (Claude Code):** escrita do código e dos testes a partir das regras e do roadmap definidos, conferindo tudo contra o manual e os dados.
- **Minha parte:** defini as restrições de custo e o escopo e discuti as decisões técnicas. Descartei o RAG vetorial por adicionar complexidade desnecessária a um manual de 8 páginas. Considerei um modelo local via Ollama para ter custo zero, mas escolhi um modelo por API (`deepseek-flash`), de custo baixo e com suporte a tool calling. Também revisei as respostas e o README e rodei testes manuais do agente com um roteiro de casos.

Os testes com o modelo real foram o que mais agregou: revelaram, por exemplo, que o e-mail compartilhado pelos clientes 11 e 43 abria o pedido de um deles, corrigido com a exigência do telefone.
