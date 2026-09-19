# Runbook: Prod OCR fallback CLIs (scanned PDF→HTML)

Host: `antiek_prod` (Ubuntu 24.04). Converter prefer order is unchanged:
**DeepSeek → ocrmypdf → tesseract** (`acquisition/doc_to_html/pdf_ocr.py`).

## Install / repair

```bash
ssh -i ~/.ssh/antiek_ed25519 root@167.235.202.98
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ocrmypdf tesseract-ocr tesseract-ocr-eng poppler-utils
```

Ansible `setup.yml` also installs these packages on fresh hosts.

## Smoke

```bash
sudo -u antiek env PATH="/opt/antiek/.venv/bin:/usr/bin:/bin" \
  /opt/antiek/.venv/bin/python -c "
from acquisition.doc_to_html import pdf_ocr
print(pdf_ocr.ocrmypdf_bin(), pdf_ocr.tesseract_bin(), pdf_ocr.pdftoppm_bin())
print('available', pdf_ocr.ocr_cli_available(), 'deepseek', pdf_ocr.deepseek_ocr_available())
"
```

Expect `ocr_cli_available=True`. DeepSeek remains Mini-only unless
`ANTIEK_OCR_BASE_URL` points at a reachable VLM.
