# Sistema de Boletim de Ocorrências

Sistema web local para lançamento e acompanhamento de ocorrências industriais.

## Como usar

Execute o arquivo `start.bat` ou rode:

```powershell
python server.py
```

Depois acesse:

```text
http://127.0.0.1:8080
```

Os dados ficam salvos no banco SQLite em `data/boletins.sqlite`.

O diretório `data/` fica fora do Git para evitar publicar registros reais com nomes, matrículas e detalhes da operação.

## Recursos

- Cadastro e edição de boletins de ocorrência.
- Numeração automática por ano.
- Campos de data, hora, turno, setor, tipo, gravidade, status, descrição, causa provável, ações e responsável.
- Indicadores de total, abertos, em tratamento, críticos e atrasados.
- Busca e filtros por status, gravidade e tipo.
- Exportação em JSON e CSV.
- Importação de backup JSON.
- Impressão da lista ou da ficha aberta.

## Banco de dados

O sistema usa SQLite por ser simples, local e não exigir instalação de servidor separado. O arquivo do banco é criado automaticamente na primeira execução.

Em produção no Render, o sistema usa PostgreSQL automaticamente quando a variável `DATABASE_URL` estiver configurada.

## Fotos

Cada boletim pode receber múltiplas fotos. As imagens são gravadas no banco de dados:

- Local: tabela `fotos` no SQLite.
- Render: tabela `fotos` no PostgreSQL, usando coluna `BYTEA`.

Por padrão, cada upload aceita até 8 fotos, com limite de 8 MB por foto. Esses limites podem ser alterados com `MAX_PHOTOS_PER_UPLOAD` e `MAX_PHOTO_MB`.

## Deploy no Render

O arquivo `render.yaml` já cria:

- Um Web Service Python.
- Um banco Render Postgres.
- A variável `DATABASE_URL` ligada ao banco.

Passos:

1. Suba o código para o GitHub.
2. No Render, crie um novo Blueprint apontando para este repositório.
3. Confirme a criação do serviço e do banco.
4. Após o deploy, acesse a URL pública gerada pelo Render.

O servidor usa `PORT` quando estiver no Render e escuta em `0.0.0.0`, como a plataforma exige para Web Services.
