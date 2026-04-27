# English Agent

MVP de um tutor de ingles por voz com FastAPI, OpenAI, transcricao,
resposta falada, correcoes leves e repeticao de palavras.

O metodo principal e bilingue: o professor orienta em portugues e a pratica
acontece em ingles. Ele fala uma frase curta em ingles, voce repete no
microfone, e depois recebe uma correcao simples.

## Funcionalidades

- Aula guiada: o agente explica em portugues e pede uma frase curta em ingles.
- Gravacao de audio pelo navegador.
- Transcricao com OpenAI Audio Transcriptions.
- Conversa com modelo de chat da OpenAI.
- Retorno estruturado com original, correcao, explicacao, resposta, repeticao e traducao de apoio.
- Texto para fala com OpenAI Audio Speech.
- Banco SQLite com frases, erros, palavras de repeticao e palavras aprendidas.
- Modo Work para vocabulario industrial simples.
- Niveis `Beginner 1` e `Beginner 2`.
- Topicos `Daily`, `Work`, `Travel` e `Routine`.
- Frase alvo para repeticao e feedback simples de fala baseado na transcricao.
- Botao `Replay` para ouvir a fala do professor novamente.

## Estrutura

```text
backend/
  main.py
  routes/audio.py
  services/
    ai_service.py
    stt_service.py
    tts_service.py
    repetition_engine.py
  database/db.py
frontend/
  index.html
  app.js
  style.css
```

## Como rodar

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edite `.env` e defina `OPENAI_API_KEY`.

```powershell
uvicorn backend.main:app --reload
```

Acesse:

```text
http://127.0.0.1:8000
```

## Como usar

1. Clique em `Iniciar aula`.
2. O professor explica em portugues o que voce vai praticar.
3. Ele fala uma frase em ingles.
4. Clique em `Gravar`, repita a frase em ingles e clique em `Parar`.
5. O agente corrige suavemente em portugues e mostra a proxima frase em ingles.

Exemplo:

```text
Professor: Vamos praticar ingles de um jeito simples.
Professor: Frase em ingles: I am ready. Repita: I am ready.
Aluno: I am ready.
Professor: Bom. Agora pratique em ingles: I am learning English.
```

Escolha `Nivel` e `Tema` no painel lateral. Use `Work` para praticar frases
simples de ambiente industrial.

O botao `Record` precisa de permissao de microfone no navegador. Use
`http://127.0.0.1:8000` ou HTTPS; alguns navegadores bloqueiam microfone em
enderecos sem contexto seguro.

O feedback de fala compara a frase alvo com o texto que a transcricao entendeu.
Ele ajuda a saber se voce repetiu bem, mas nao substitui uma analise fonetica
profunda.

## Endpoints

- `GET /api/health`
- `POST /api/audio/start`
- `POST /api/audio/conversation`
- `GET /api/audio/progress/{user_id}`

## Deploy

O projeto inclui `Dockerfile` e `render.yaml`. Em uma hospedagem como Render:

1. Conecte este repositorio.
2. Crie um Web Service via Docker.
3. Defina `OPENAI_API_KEY` nas variaveis de ambiente da plataforma.
4. Use o HTTPS gerado pela plataforma para liberar microfone no navegador.

Tambem e possivel rodar com Docker local:

```powershell
docker build -t english-agent .
docker run --env-file .env -p 8000:8000 english-agent
```

## Variaveis principais

- `OPENAI_API_KEY`
- `OPENAI_CHAT_MODEL`
- `OPENAI_STT_MODEL`
- `OPENAI_TTS_MODEL`
- `OPENAI_TTS_VOICE`
- `DATABASE_PATH`
