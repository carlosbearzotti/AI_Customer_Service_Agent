# 04_pedido_e_arrependimento

**Cliente:** Cadê meu pedido 8?

**Tom:** Bom dia! Pra eu consultar o pedido 8, preciso do e-mail ou telefone usado na compra. Pode me informar?

**Cliente:** Meu e-mail é anacarol.ferreira@coldmail.com

> `consultar_pedido({'pedido_id': 8, 'email_ou_telefone': 'anacarol.ferreira@coldmail.com'})`

**Tom:** Ana, achei seu pedido 8! Ele já foi enviado. 🎉

- **Item:** Kala KA-C Concert Mogno (1 unidade)
- **Status:** enviado
- **Código de rastreio:** BRJL5544332BR
- **Previsão de entrega:** 28/02/2026
- **Total:** R$ 349,90 (pago no débito)

Você pode acompanhar pelo site dos Correios com esse código. Precisa de mais alguma coisa?

**Cliente:** Me arrependi da compra, posso devolver?

> `consultar_politica({'secao': '4'})`

**Tom:** Pode sim, Ana! Pelo direito de arrependimento (compras online), você tem até **7 dias corridos após o recebimento** pra solicitar a devolução, sem precisar justificar.

Condições:
- Produto na **embalagem original**, sem sinais de uso, com todos os acessórios e manuais
- Reembolso na **mesma forma de pagamento** (no seu caso, débito) em até **10 dias úteis**
- O **frete de devolução é por conta da loja**

Pra eu verificar se você está dentro do prazo, me informa a **data em que recebeu** o pedido?

**Cliente:** Recebi em 2026-03-20

> `avaliar_prazo({'tipo': 'arrependimento', 'data_compra': '2026-02-15', 'data_recebimento': '2026-03-20'})`

**Tom:** Boa notícia, Ana: você está **dentro do prazo** — 5 dias corridos desde o recebimento, e o limite é **27/03/2026**.

Então, resumindo:
- Devolução por arrependimento, sem justificativa
- Produto na embalagem original, sem sinais de uso, com acessórios e manuais
- Reembolso no débito em até 10 dias úteis
- Frete de devolução por conta da loja

Eu não consigo abrir a devolução sozinho, então vou registrar um protocolo pra nossa equipe dar sequência. Confirma pra mim? E me passa um telefone de contato, por favor.

**Cliente:** Sim, pode registrar a devolução

> `registrar_atendimento_humano({'tipo': 'arrependimento', 'contato': 'anacarol.ferreira@coldmail.com', 'pedido_id': 8, 'resumo': 'Cliente Ana solicita devolução por arrependimento do pedido 8 (Kala KA-C Concert Mogno, 1 unidade, R$ 349,90, pago no débito). Recebimento informado em 2026-03-20; prazo de arrependimento confirmado como elegível, com data limite 2026-03-27. Produto a devolver na embalagem original, sem sinais de uso, com acessórios e manuais. Reembolso na mesma forma de pagamento em até 10 dias úteis; frete de devolução por conta da loja.'})`

**Tom:** Prontinho, Ana! Devolução registrada. ✅

- **Protocolo:** 1
- **Pedido:** 8 — Kala KA-C Concert Mogno
- **Prazo de arrependimento:** dentro do prazo (limite 27/03/2026)

A equipe entra em contato pra combinar a devolução. O reembolso vai na mesma forma de pagamento (débito) em até 10 dias úteis, e o frete de devolução é por conta da loja.

Só lembra de manter o produto na embalagem original, sem sinais de uso, com todos os acessórios e manuais. Precisa de mais alguma coisa?
