curl -X POST -H 'Content-Type: application/json' \
  -d '{"username": "secure-ds-access-sa", "email": "demo-sa@customer.com"}' \
  $DOMINO_API_PROXY/v4/serviceAccounts

export IDPID=294076b7-f800-4963-be49-6f635b933159

curl -X POST -H 'Content-Type: application/json' \
  -d '{"name": "secure-ds-access-sa-token-1"}' \
  $DOMINO_API_PROXY/v4/serviceAccounts/$IDPID/tokens