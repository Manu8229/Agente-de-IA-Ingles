# English Agent

MVP de um tutor de ingles por voz com FastAPI, OpenAI, transcricao, resposta falada, correcoes leves e repeticao de palavras.

## Funcionalidades

- Gravacao de audio pelo navegador.
- Transcricao com OpenAI Audio Transcriptions.
- Conversa com modelo de chat da OpenAI.
- Retorno estruturado com original, correcao, explicacao, resposta e repeticao.
- Texto para fala com OpenAI Audio Speech.
- Banco SQLite com frases, erros, palavras de repeticao e palavras aprendidas.
- Modo Work para vocabulario industrial simples.

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

## Endpoints

- `GET /api/health`
- `POST /api/audio/conversation`
- `GET /api/audio/progress/{user_id}`

## Variaveis principais

- `OPENAI_API_KEY`
- `OPENAI_CHAT_MODEL`
- `OPENAI_STT_MODEL`
- `OPENAI_TTS_MODEL`
- `OPENAI_TTS_VOICE`
- `DATABASE_PATH`
