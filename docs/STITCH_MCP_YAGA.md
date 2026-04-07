# © YAGA Project — Todos los derechos reservados
# Google Stitch MCP — Guía de integración para YAGA + Poleana

> Google Stitch genera UI de alta fidelidad desde prompts de texto usando Gemini.
> El MCP conecta esos diseños directamente al flujo de desarrollo con Claude Code.
> Configurado en: `~/.claude/settings.json` · Paquete: `@_davideast/stitch-mcp@0.5.3`

---

## 1. Herramientas disponibles via MCP

| Herramienta | Parámetros | Qué hace |
|-------------|-----------|---------|
| `create_project` | `name`, `description` | Crea un nuevo proyecto en stitch.withgoogle.com |
| `generate_screen_from_text` | `project_id`, `prompt`, `screen_name` | Genera una pantalla con Gemini desde descripción en texto |
| `get_screen` | `project_id`, `screen_id` | Obtiene metadata de una pantalla (colores, tipografía, layout) |
| `get_screen_code` | `project_id`, `screen_id` | Descarga el HTML generado por Stitch |
| `get_screen_image` | `project_id`, `screen_id` | Descarga screenshot de la pantalla como base64 |
| `build_site` | `project_id`, `routes` | Construye el sitio completo mapeando pantallas a rutas |

---

## 2. Flujo de trabajo general

```
[Prompt en Stitch] → [Gemini genera diseño] → [Claude Code via MCP]
       ↓                                               ↓
  stitch.withgoogle.com                    get_screen_code(project_id, screen_id)
                                                       ↓
                                           HTML de alta fidelidad
                                                       ↓
                                       Adaptar a frontend/index.html (YAGA)
                                       o Poleana_Project/web/poleana_game.html
```

---

## 3. Comandos para YAGA.app

### 3.1 Crear el proyecto YAGA en Stitch

```
Herramienta: create_project
Parámetros:
  name: "YAGA — Co-piloto para conductores"
  description: "PWA fintech para conductores Uber/DiDi en México. Modo oscuro, alto contraste, lectura periférica, diseñado para ser usado mientras se maneja."
```

### 3.2 Pantallas a generar para YAGA

#### Dashboard Cockpit (tab JORNADA)
```
Herramienta: generate_screen_from_text
Prompt:
  "Dashboard financiero para conductor de Uber. Fondo negro #0a0a0a. 
   Métricas grandes y legibles: viajes completados hoy (número grande), 
   ingreso bruto MXN (verde #00ff88), gastos operativos (rojo), 
   ganancia neta (verde brillante). Barra de desglose del día abajo. 
   Lista de últimos 5 viajes. Input de voz en la parte inferior con botón 
   micrófono. Diseño para lectura periférica mientras se conduce: 
   texto blanco sobre negro, sin distracciones, fuentes grandes."
screen_name: "dashboard_cockpit"
```

#### Pantalla de Login / Registro
```
Herramienta: generate_screen_from_text
Prompt:
  "Pantalla de autenticación para app fintech de conductores. 
   Modo oscuro, logo YAGA arriba. Tabs: Entrar / Crear cuenta. 
   Formulario minimal: email, contraseña, checkbox 'Recordarme'. 
   Botón principal verde #00ff88. Link '¿Olvidaste tu contraseña?' 
   en gris debajo del botón. Estilo limpio, profesional, mobile-first."
screen_name: "auth_login"
```

#### Pantalla Forgot Password
```
Herramienta: generate_screen_from_text
Prompt:
  "Pantalla de recuperación de contraseña. Modo oscuro. 
   Texto explicativo breve en gris. Campo de email. 
   Botón 'Enviar enlace' en verde. Link '← Volver al inicio de sesión'. 
   Estado de éxito: mensaje de confirmación con fondo verde suave."
screen_name: "forgot_password"
```

#### Tab VEHÍCULO — Mantenimiento
```
Herramienta: generate_screen_from_text
Prompt:
  "Pantalla de mantenimiento vehicular para conductor. Modo oscuro. 
   Cards para: cambio de aceite, llantas, frenos, servicio general. 
   Cada card muestra: nombre del servicio, última fecha, próxima fecha, 
   indicador de estado (verde/amarillo/rojo según urgencia). 
   Botón flotante '+' para agregar nuevo mantenimiento. 
   Colores: fondo #0a0a0a, cards #1a1a1a, acentos #00ff88."
screen_name: "vehiculo_mantenimiento"
```

#### Tab MAPA — GPS Dashboard
```
Herramienta: generate_screen_from_text
Prompt:
  "Dashboard GPS para conductor activo. Modo oscuro. 
   Mapa de fondo (placeholder oscuro). Stats superpuestos: 
   velocidad actual (grande, centro), distancia recorrida, 
   tiempo activo. Badge de estado: 'GPS Activo' en verde 
   o 'GPS Pausado' en amarillo. Botones: Iniciar/Pausar tracking. 
   Diseño para glanceable — el conductor no debe apartar la vista."
screen_name: "gps_dashboard"
```

#### Pantallas ARCO (Derechos de privacidad)
```
Herramienta: generate_screen_from_text
Prompt:
  "Pantalla de derechos de privacidad ARCO (México, LFPDPPP). 
   Modo oscuro. 4 opciones en cards:
   - Acceso: 'Ver mis datos' con ícono de ojo
   - Rectificación: 'Actualizar mis datos' con ícono de edición
   - Cancelación: 'Eliminar mi cuenta' con ícono de advertencia rojo
   - Oposición: toggles para marketing/investigación
   Header con escudo de privacidad. Texto claro sobre qué datos se manejan."
screen_name: "arco_privacidad"
```

### 3.3 Construir el sitio YAGA completo
```
Herramienta: build_site
Parámetros:
  project_id: <ID del proyecto YAGA creado>
  routes: {
    "/": "dashboard_cockpit",
    "/auth": "auth_login",
    "/auth/forgot": "forgot_password",
    "/vehiculo": "vehiculo_mantenimiento",
    "/mapa": "gps_dashboard",
    "/privacidad": "arco_privacidad"
  }
```

### 3.4 Obtener código para integrar
```
Herramienta: get_screen_code
Parámetros:
  project_id: <ID proyecto YAGA>
  screen_id: "dashboard_cockpit"

→ Claude Code recibe el HTML generado por Stitch
→ Adaptar colores/variables al sistema de YAGA (#00ff88, #0a0a0a, var(--accent))
→ Integrar en la sección correspondiente de frontend/index.html
```

---

## 4. Comandos para Poleana

### 4.1 Crear proyecto Poleana en Stitch
```
Herramienta: create_project
Parámetros:
  name: "Poleana — Juego de mesa mexicano online"
  description: "Juego de mesa tradicional mexicano, multijugador online. 
                Tablero físico digitalizado. Modos: local, vs CPU, online 2-4 jugadores. 
                Estética mexicana colorida con elementos de tablero de juego."
```

### 4.2 Pantallas a generar para Poleana

#### Menú principal
```
Herramienta: generate_screen_from_text
Prompt:
  "Menú principal de juego de mesa mexicano 'Poleana'. 
   Fondo oscuro con elementos decorativos de tablero de juego. 
   Logo 'POLEANA' grande arriba. 4 botones de modo de juego:
   - 1 jugador vs CPU (ícono robot)
   - 2 jugadores mismo dispositivo (ícono dos personas)
   - Online multijugador (ícono wifi/red)  
   Badge de estado del servidor: 'Online' verde o 'Offline' rojo.
   Estética colorida y festiva, tipografía bold."
screen_name: "menu_principal"
```

#### Lobby / Sala de espera online
```
Herramienta: generate_screen_from_text
Prompt:
  "Pantalla de sala de espera para juego online multijugador. 
   Código de sala grande y copiable (ej: 'SALA-4829'). 
   Lista de jugadores conectados con avatares/iniciales. 
   Indicador de 'Esperando jugadores...' animado. 
   Botón 'Iniciar partida' verde (activo cuando hay 2+ jugadores). 
   Botón 'Copiar invitación' para compartir el código. 
   Chat simple de texto entre jugadores en la sala."
screen_name: "lobby_online"
```

#### Tablero de juego
```
Herramienta: generate_screen_from_text
Prompt:
  "Tablero digital del juego de mesa Poleana mexicano. 
   Tablero cuadrado con casillas numeradas alfanuméricas (A1-Z26). 
   Fichas de colores para cada jugador (4 colores: rojo, azul, verde, amarillo). 
   Panel lateral derecho: turno actual, dados, historial de movimientos. 
   Botón central 'Tirar Dados' prominente. 
   Indicador claro de '¡Es tu turno!' en modo online. 
   Diseño que recuerde al tablero físico tradicional."
screen_name: "tablero_juego"
```

#### Pantalla de resultados / fin de partida
```
Herramienta: generate_screen_from_text
Prompt:
  "Pantalla de victoria en juego de mesa. Confeti animado. 
   Nombre del ganador grande al centro. 
   Tabla de posiciones con todos los jugadores y sus puntos. 
   Botones: 'Revancha' y 'Menú principal'. 
   Estética festiva y colorida mexicana."
screen_name: "pantalla_victoria"
```

### 4.3 Build del sitio Poleana
```
Herramienta: build_site
Parámetros:
  project_id: <ID proyecto Poleana>
  routes: {
    "/": "menu_principal",
    "/sala": "lobby_online",
    "/juego": "tablero_juego",
    "/resultado": "pantalla_victoria"
  }
```

---

## 5. Flujo de integración con Claude Code

### Paso a paso para cada pantalla:

```
1. GENERAR en Stitch (via MCP o en stitch.withgoogle.com)
   → generate_screen_from_text(project_id, prompt, screen_name)

2. OBTENER el código HTML
   → get_screen_code(project_id, screen_id)
   → Claude recibe el HTML completo con estilos inline

3. ANALIZAR el diseño
   → get_screen_image(project_id, screen_id)
   → Ver screenshot para validar el diseño visualmente

4. ADAPTAR al proyecto
   Para YAGA:
   - Reemplazar colores Stitch por variables CSS de YAGA
     (primary: #00ff88, bg: #0a0a0a, danger: #ff4444)
   - Adaptar estructura al HTML monolítico de frontend/index.html
   - Mantener JS vanilla (sin React ni frameworks)
   - Verificar touch targets ≥48px para uso en auto
   
   Para Poleana:
   - Integrar en poleana_game.html
   - Conectar con el motor poleana_engine.js
   - Mantener compatibilidad con modo offline

5. DESPLEGAR
   Para YAGA:
   scp frontend/index.html ec2-user@EC2:~/yaga-project/frontend/index.html
   
   Para Poleana:
   rsync web/ ec2-user@EC2:~/Poleana_Project/web/
```

---

## 6. Prompts reutilizables — Sistema de diseño YAGA

Incluir en todos los prompts de YAGA para coherencia visual:

```
Sistema de diseño YAGA:
- Fondo principal: #0a0a0a (negro)
- Fondo cards: #1a1a1a
- Color acento / positivo: #00ff88 (verde brillante)
- Color peligro / negativo: #ff4444 (rojo)
- Color advertencia: #f5a623 (amarillo/naranja)
- Color texto principal: #ffffff
- Color texto secundario: #888888 (muted)
- Fuente: sistema (San Francisco, Segoe UI, Roboto)
- Border radius: 12px en cards, 8px en botones
- Modo: EXCLUSIVAMENTE oscuro
- Mobile-first, touch targets mínimo 48x48px
- Sin animations complejas — priorizar performance
- El usuario es un conductor en movimiento — simplicidad máxima
```

---

## 7. Mejoras esperadas en el proyecto

### Para YAGA.app
| Área | Situación actual | Con Stitch MCP |
|------|-----------------|---------------|
| Dashboard cockpit | HTML con CSS inline manual | Diseño generado por Gemini, sistema de colores consistente |
| Pantallas ARCO | No implementadas visualmente | Prototipos de alta fidelidad en minutos |
| Onboarding | Login básico sin flujo de bienvenida | Pantalla de bienvenida + tutorial para primer uso |
| Modo vehículo | Cards básicos con CSS minimal | Cards visuales con indicadores de estado mejorados |
| Responsive | Optimizado para mobile pero no tablet | Layouts adaptables generados por Stitch |

### Para Poleana
| Área | Situación actual | Con Stitch MCP |
|------|-----------------|---------------|
| Menú principal | HTML funcional sin refinamiento visual | Menú con identidad visual consistente |
| Lobby online | Formulario básico de código de sala | UI de sala de espera con lista de jugadores |
| Tablero | Canvas/grid programático | Referencia visual de alta fidelidad para mejorar el tablero |
| Estados de juego | Mensajes de texto plano | Indicadores visuales claros (turno, dados, movimientos válidos) |
| Offline badge | Badge de texto simple | Indicador visual prominente de modo offline |

---

## 8. Ejemplos de prompts rápidos (copy-paste)

```bash
# En Claude Code, una vez activo el MCP de Stitch:

# Generar diseño del cockpit
"Usa stitch MCP para generar la pantalla del dashboard cockpit de YAGA: 
fondo negro, métricas de viajes y ganancias en verde #00ff88, 
botón de micrófono abajo para comandos de voz. 
Luego obtén el código HTML y adáptalo a frontend/index.html."

# Generar diseño del menú de Poleana  
"Usa stitch MCP para crear el menú principal de Poleana con 4 modos de juego, 
badge de estado del servidor online/offline, y estética de juego de mesa mexicano. 
Integra el HTML resultante en Poleana_Project/web/poleana_game.html."

# Actualizar pantalla existente
"Usa get_screen_code de stitch con project_id=X, screen_id=dashboard_cockpit, 
y compara el diseño con el actual frontend/index.html. 
Propón mejoras de UX basadas en el diseño de Stitch."
```

---

## 9. Verificación de la conexión

```bash
# Confirmar que el MCP está corriendo correctamente
# En Claude Code, prueba este comando:
"Lista los proyectos disponibles en mi cuenta de Stitch"

# Si hay error de auth, verificar:
cat ~/.claude/settings.json | grep STITCH_API_KEY

# Regenerar API key si es necesario:
# → stitch.withgoogle.com → Perfil → Stitch Settings → API key → Create key
```

---

## Referencias

- [Documentación oficial Stitch MCP](https://stitch.withgoogle.com/docs/mcp/setup/)
- [GitHub davideast/stitch-mcp](https://github.com/davideast/stitch-mcp)
- [npm @_davideast/stitch-mcp](https://www.npmjs.com/package/@_davideast/stitch-mcp)
- [Codelab Design-to-Code con Stitch](https://codelabs.developers.google.com/design-to-code-with-antigravity-stitch)
- [Google Stitch MCP + Claude Code — guía de integración](https://www.sotaaz.com/post/stitch-mcp-integration-en)
