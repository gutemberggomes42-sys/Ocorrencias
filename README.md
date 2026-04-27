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
