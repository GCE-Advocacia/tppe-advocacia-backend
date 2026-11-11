"""Envia um e-mail de teste pela cadeia configurada no .env.

Uso: python -m scripts.send_test_email destino@exemplo.com [--provider smtp|resend]

Serve para validar a senha de app do Gmail (ou o Resend) sem subir a API.
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.config.settings import get_settings
from app.modules.email.errors import EmailSendError
from app.modules.email.factory import build_from_configs, configs_from_settings
from app.modules.email.protocol import EmailMessage


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("to", help="destinatário")
    parser.add_argument(
        "--provider",
        choices=["smtp", "resend"],
        help="testa só este provedor, sem failover",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    configs = configs_from_settings(get_settings())
    if args.provider:
        configs = [c for c in configs if type(c).__name__.lower().startswith(args.provider)]
    if not configs:
        print("Nenhum provedor configurado. Confira EMAIL_PROVIDERS e SMTP_* no .env.")
        return 1

    service = build_from_configs(configs)
    print(f"Cadeia: {' -> '.join(service.provider_names)}")
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    message = EmailMessage(
        to=[args.to],
        subject=f"Teste de envio ({now})",
        html=f"<p>E-mail de teste enviado em <b>{now}</b>.</p>",
        text=f"E-mail de teste enviado em {now}.",
    )
    try:
        result = service.deliver(message)
    except EmailSendError as err:
        print(f"FALHOU: {err!r}")
        return 1
    print(
        f"OK: provider={result.provider} message_id={result.message_id} "
        f"({result.duration_ms} ms)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
