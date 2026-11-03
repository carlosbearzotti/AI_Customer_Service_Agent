# 04_pedido_e_arrependimento

**Cliente:** Cadê meu pedido 8?

**Carlos:** Bom dia! Pra eu consultar o pedido 8, preciso do e-mail ou telefone usado na compra. Pode me informar?

**Cliente:** Meu e-mail é anacarol.ferreira@coldmail.com

> `consultar_pedido({'pedido_id': 8, 'email_ou_telefone': 'anacarol.ferreira@coldmail.com'})`

**Carlos:** Ana, achei seu pedido 8! Ele já foi enviado. 🎉

- **Item:** Kala KA-C Concert Mogno (1 unidade)
- **Status:** enviado
- **Código de rastreio:** BRJL5544332BR
- **Previsão de entrega:** 28/02/2026
- **Total:** R$ 349,90 (pago no débito)

É só acompanhar pelo código no site dos Correios. Precisa de mais alguma coisa?

**Cliente:** Me arrependi da compra, posso devolver?

> `consultar_politica({'secao': '4'})`

**Carlos:** Claro, Ana! Pelo direito de arrependimento dá pra devolver em até **7 dias corridos após o recebimento**, sem precisar justificar. As condições são:

- Produto na **embalagem original**, sem sinais de uso, com todos os acessórios e manuais
- Reembolso na **mesma forma de pagamento** (no seu caso, débito) em até **10 dias úteis**
- O **frete de devolução é por conta da loja**

Pra eu verificar se você está dentro do prazo, me conta: **qual foi a data em que você recebeu o pedido?**

**Cliente:** Recebi em 2026-03-20

> `avaliar_prazo({'tipo': 'arrependimento', 'data_compra': '2026-02-15', 'data_recebimento': '2026-03-20'})`

**Carlos:** Boa notícia, Ana: você está **dentro do prazo** — 5 dias corridos desde o recebimento, e o limite é **27/03/2026**.

Então dá pra seguir com a devolução por arrependimento, com essas condições:
- Produto na embalagem original, sem sinais de uso, com todos os acessórios e manuais
- Reembolso na mesma forma de pagamento (débito) em até 10 dias úteis
- Frete de devolução por conta da loja

Quer que eu já abra um protocolo com a equipe pra dar andamento na devolução?

**Cliente:** Sim, pode registrar a devolução

> `registrar_atendimento_humano({'tipo': 'arrependimento', 'contato': 'anacarol.ferreira@coldmail.com', 'pedido_id': 8, 'resumo': 'Cliente Ana solicita devolução por arrependimento do pedido 8 (Kala KA-C Concert Mogno, 1 unidade, total R$ 349,90, pago no débito). Recebimento informado em 2026-03-20; prazo de arrependimento confirmado como dentro do limite (data limite 2026-03-27).'})`

**Carlos:** Prontinho, Ana! Devolução registrada. ✅

- **Protocolo:** 1
- A equipe entra em contato pra combinar a devolução
- Reembolso na mesma forma de pagamento (débito) em até **10 dias úteis**
- Frete de devolução por conta da loja

Só lembra de manter o produto na embalagem original, sem sinais de uso, com todos os acessórios e manuais. Precisa de mais alguma coisa?
