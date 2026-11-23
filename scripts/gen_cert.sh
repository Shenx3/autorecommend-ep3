#!/bin/bash
# Genera un certificado TLS autofirmado para nginx (declaralo asi en el informe)
set -e
mkdir -p certs
openssl req -x509 -nodes -days 30 -newkey rsa:2048 \
  -keyout certs/key.pem -out certs/cert.pem -subj "/CN=autorecommend"
echo "Certificado generado en certs/"
