# YAGA — Workflow de Registro por Voz

Diagrama verificado contra `frontend/index.html`, `app/api/v1/nlp.py`, `app/services/nlp/classifier.py` y `app/services/jornada_service.py`.

---

## Flujo principal (happy path)

```mermaid
sequenceDiagram
    participant C as Conductor
    participant B as Navegador (Chrome/Edge)
    participant SR as Web Speech API
    participant FE as Frontend (index.html)
    participant API as FastAPI :8000
    participant AUTH as decode_token (HS256)
    participant NLP as classify()
    participant SVC as jornada_service
    participant DB as PostgreSQL 16

    C->>B: Presiona boton microfono
    B->>SR: recognition.start()
    SR->>SR: Escucha audio (es-MX)
    SR->>FE: onresult → transcript

    FE->>FE: cmdInput.value = transcript
    FE->>API: POST /api/v1/command<br/>Headers: Authorization: Bearer {JWT}<br/>Body: { text: transcript }

    API->>AUTH: get_current_user(token)
    AUTH->>AUTH: jwt.decode(token, JWT_SECRET, HS256)
    AUTH->>DB: SELECT Usuario WHERE id = sub AND deleted_at IS NULL
    AUTH-->>API: Usuario objeto

    API->>NLP: classify(text)
    NLP->>NLP: normalize(text) → NFKD lowercase
    NLP->>NLP: match keywords → IntentPattern
    NLP->>NLP: extract_entities(text) → monto, plataforma, metodo_pago
    NLP-->>API: ClassificationResult(intent, entities)

    alt intent == REGISTRAR_VIAJE
        API->>SVC: get_or_create_jornada(conductor_id)
        SVC->>DB: SELECT jornadas WHERE conductor_id AND fecha=today AND estado='activa'
        DB-->>SVC: jornada_id (o INSERT si no existe)
        API->>SVC: registrar_viaje(jornada_id, entities)
        SVC->>DB: INSERT INTO viajes (jornada_id, monto, propina, plataforma, metodo_pago)
        DB-->>SVC: Row insertado
        SVC-->>API: { id, monto, propina, plataforma, metodo_pago }
    else intent == REGISTRAR_GASTO
        API->>SVC: get_or_create_jornada(conductor_id)
        SVC->>DB: SELECT/INSERT jornadas
        API->>SVC: registrar_gasto(jornada_id, entities)
        SVC->>DB: INSERT INTO gastos (jornada_id, monto, categoria)
        DB-->>SVC: Row insertado
        SVC-->>API: { id, monto, categoria }
    end

    API-->>FE: { intent, message, data }

    FE->>FE: showToast(message, 'success')
    FE->>API: GET /api/v1/resumen<br/>Headers: Authorization: Bearer {JWT}
    API->>SVC: get_resumen_jornada(conductor_id)
    SVC->>DB: SELECT viajes + gastos WHERE jornada activa
    DB-->>SVC: Datos agregados
    SVC-->>API: { total_viajes, ingresos_brutos, total_gastos, ganancia_neta, detalles }
    API-->>FE: Resumen JSON

    FE->>FE: renderResumen(data)
    FE->>C: Dashboard actualizado
```

---

## Flujo de clasificacion NLP (detalle)

```mermaid
flowchart TD
    A[Texto del conductor] --> B[normalize: NFKD + lowercase + remove accents]
    B --> C{Interceptor: contiene 'cerrar' + 'jornada'?}
    C -->|Si| D[cerrar_jornada directamente]
    D --> E[get_comparativa → estado]
    E --> F[Response: jornada cerrada + resumen]

    C -->|No| G[classify: iterar INTENT_PATTERNS]
    G --> H{Algun keyword matched?}
    H -->|No| I[UNKNOWN → toast con sugerencia]
    H -->|Si| J[Calcular score por intent]
    J --> K[Seleccionar intent con mayor score]
    K --> L[extract_entities]

    L --> M{Intent?}
    M -->|REGISTRAR_VIAJE| N{monto presente?}
    N -->|No| O[Pedir monto: 'viaje uber efectivo 90']
    N -->|Si| P[get_or_create_jornada]
    P --> Q[INSERT INTO viajes]

    M -->|REGISTRAR_GASTO| R{monto presente?}
    R -->|No| S[Pedir monto: 'gasolina 300']
    R -->|Si| T[get_or_create_jornada]
    T --> U[INSERT INTO gastos]

    M -->|CONSULTAR_RESUMEN| V[get_resumen_jornada]
    M -->|CERRAR_JORNADA| D
    M -->|INICIAR_JORNADA| W[get_or_create_jornada solo]
    M -->|CONSULTAR_TOTAL| V
```

---

## Flujos de error

```mermaid
flowchart TD
    subgraph "Error: Sin conexion"
        E1[sendCommand fetch] -->|catch: network error| E2["showToast('Sin conexion con el servidor', 'error')"]
        E2 --> E3[statusDot → rojo]
        E3 --> E4[cmdInput se rehabilita]
    end

    subgraph "Error: Token expirado (401)"
        T1[fetch /api/v1/resumen] -->|res.status === 401| T2[clearInterval resumenInterval]
        T2 --> T3[clearSession: _authToken = null + limpiar storage]
        T3 --> T4[authScreen visible → usuario debe hacer login]
    end

    subgraph "Error: Intent UNKNOWN"
        U1[classify retorna UNKNOWN] --> U2["Response: {intent: 'unknown', message: 'No entendi...'}"]
        U2 --> U3["showToast('No entendi. Intenta: viaje uber efectivo 90 o gasolina 300')"]
        U3 --> U4[data === null → no se llama fetchResumen]
    end

    subgraph "Error: Firefox sin SpeechRecognition"
        F1{webkitSpeechRecognition in window?} -->|No| F2[btnMic deshabilitado visualmente]
        F2 --> F3["btnMic.textContent = prohibido"]
        F3 --> F4["Banner: 'Microfono inactivo en Firefox — usa Chrome o Edge para voz'"]
        F4 --> F5[Click en btnMic → showToast error]
        F1 -->|Si| F6[recognition inicializado normalmente]
    end

    subgraph "Error: Audio no capturado"
        A1[recognition.onerror] --> A2[Remover clase 'listening']
        A2 --> A3["showToast('No se pudo capturar audio', 'error')"]
    end
```

---

## Flujo de sesion (lifecycle completo)

```mermaid
stateDiagram-v2
    [*] --> PageLoad

    PageLoad --> CheckToken: getToken() + getYaga('yaga_conductor_id')

    CheckToken --> MostrarAuth: token null O conductor_id null
    CheckToken --> ValidarSesion: ambos presentes

    ValidarSesion --> Dashboard: GET /auth/me → 200 OK
    ValidarSesion --> MostrarAuth: GET /auth/me → 401
    ValidarSesion --> Dashboard: GET /auth/me → network error (offline mode)

    MostrarAuth --> Login: usuario ingresa credenciales
    Login --> Dashboard: POST /auth/login → 200
    Login --> MostrarAuth: POST /auth/login → 401

    Dashboard --> Polling: setInterval(fetchResumen, 30000)
    Dashboard --> Comando: sendCommand(text)
    Comando --> Dashboard: response OK → fetchResumen

    Polling --> MostrarAuth: 401 → clearInterval + clearSession
    Comando --> Dashboard: network error → toast

    Dashboard --> Logout: click cerrar sesion
    Logout --> MostrarAuth: clearSession()

    note right of PageLoad
        Al recargar la pagina _authToken = null
        El usuario siempre debe hacer login de nuevo
        (JWT en memoria, no en storage)
    end note
```

---

## Notas tecnicas

1. **Web Speech API** solo esta disponible en Chrome y Edge. Firefox no implementa `webkitSpeechRecognition` ni `SpeechRecognition`. El frontend detecta esto al cargar y muestra un banner permanente.

2. **Latencia del clasificador NLP:** El clasificador es determinista por keywords, sin modelo ML ni llamada a API externa. La latencia es sub-1ms en el servidor. El cuello de botella es la red y la query a PostgreSQL.

3. **Polling vs WebSocket:** El dashboard se actualiza via polling cada 30 segundos (`setInterval(fetchResumen, 30000)`). No hay WebSocket para el dashboard (solo Poleana usa WebSocket).

4. **Jornada automatica:** Si no existe jornada activa para hoy, `get_or_create_jornada` crea una automaticamente al primer comando del dia. El conductor no necesita decir "iniciar jornada" explicitamente.

5. **conductor_id en body:** El frontend envia `conductor_id` en el body de `/command` como legacy, pero el backend lo ignora — usa `current_user.id` del token JWT.
