

# ☁️ icloud-cli-tools

> Accede al **Calendario**, **Recordatorios**, **Notas** y dispositivos **Buscar** de iCloud desde la terminal de Linux.

[![CI](https://github.com/alan13367/icloud-cli-tools/actions/workflows/ci.yml/badge.svg)](https://github.com/alan13367/icloud-cli-tools/actions)
[![PyPI](https://img.shields.io/pypi/v/icloud-cli-tools.svg)](https://pypi.org/project/icloud-cli-tools/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-green.svg)](https://python.org)

## Características

- 📅 **Calendario** — Lista, crea y elimina eventos con análisis de fechas naturales
- ✅ **Recordatorios** — Gestiona recordatorios entre listas, marca como completados, establece prioridades
- 📝 **Notas** — Lee, crea y busca tus Notas de iCloud
- 📍 **Buscar** — Ubica dispositivos, reproduce sonidos y activa el Modo Perdido
- 🔄 **Sincronización en segundo plano** — Daemon con integración de systemd para caché periódico
- 🔐 **Autenticación segura** — Soporte para 2FA, llavero del SO para credenciales y caché de sesiones
- 🎨 **Salida atractiva** — Tablas enriquecidas, JSON y formatos de texto sin formato

## Instalación

```bash
# Desde PyPI (recomendado)
pip install icloud-cli-tools
```

O instala desde el código fuente:

```bash
# Clona el repositorio
git clone https://github.com/alan13367/icloud-cli-tools.git
cd icloud-cli-tools

# Configura un entorno virtual (recomendado, obligatorio en Debian/Ubuntu modernos)
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

> **Consejo:** Para usar `icloud-cli` sin activar el entorno virtual cada vez, añade un alias:
> ```bash
> echo 'alias icloud-cli="~/icloud-cli-tools/.venv/bin/icloud-cli"' >> ~/.bashrc
> source ~/.bashrc
> ```

## Inicio rápido

```bash
# 1. Inicia sesión en tu cuenta de iCloud
icloud-cli login

# 2. Configura el acceso a Notas (requiere una contraseña específica para aplicaciones)
icloud-cli notes setup-imap

# 3. ¡Empieza a usarlo!
icloud-cli calendar list
icloud-cli reminders list
icloud-cli notes list
icloud-cli findmy list
```

## Uso

### Autenticación

```bash
icloud-cli login          # Inicio de sesión interactivo con 2FA
icloud-cli logout         # Limpia todas las credenciales almacenadas
icloud-cli status         # Verifica el estado de autenticación
```

### Calendario

```bash
icloud-cli calendar list                    # Eventos para los próximos 7 días
icloud-cli calendar list --from today --to tomorrow
icloud-cli calendar show <event-id>
icloud-cli calendar add -t "Meeting" -s "2025-06-15 10:00" -e "2025-06-15 11:00"
icloud-cli calendar delete <event-id>
```

### Recordatorios

```bash
icloud-cli reminders list                   # Todos los recordatorios activos
icloud-cli reminders list --list "Shopping" --completed
icloud-cli reminders add -t "Buy milk" -d "2025-06-15" -l "Shopping"   # fecha simple -> recordatorio todo el día
icloud-cli reminders add -t "Standup" -d "2025-06-15 09:30"            # fecha + hora -> recordatorio programado
icloud-cli reminders complete <reminder-id>
icloud-cli reminders delete <reminder-id>
```

### Notas

```bash
icloud-cli notes list
icloud-cli notes show <note-id>
icloud-cli notes add -t "My Note" -b "Note content here"
icloud-cli notes search "keyword"
```

> **Nota:** El acceso a Notas requiere una contraseña específica para aplicaciones. Genera una en
> [appleid.apple.com](https://appleid.apple.com/account/manage) →
> *Iniciar sesión y seguridad* → *Contraseñas específicas para aplicaciones*.

### Buscar

```bash
icloud-cli findmy list                      # Todos los dispositivos con su estado
icloud-cli findmy locate "iPhone"           # Coordenadas GPS + enlace a Maps
icloud-cli findmy play-sound "iPhone"       # Hace sonar tu dispositivo
icloud-cli findmy lost-mode "iPhone" -p "+1234567890" -m "Please return"
```

### Sincronización y Daemon

```bash
icloud-cli sync                # Sincronización única al caché local
icloud-cli daemon start        # Inicia la sincronización en segundo plano (cada 15 min)
icloud-cli daemon stop         # Detiene el daemon
icloud-cli daemon status       # Verifica el estado del daemon
```

#### Integración con Systemd (Linux)

```bash
# Instala el servicio
cp systemd/icloud-cli-sync.service ~/.config/systemd/user/
systemctl --user enable icloud-cli-sync
systemctl --user start icloud-cli-sync
```

### Formatos de salida

```bash
icloud-cli calendar list -f table   # Tabla con formato enriquecido (predeterminado)
icloud-cli calendar list -f json    # JSON legible por máquina
icloud-cli calendar list -f plain   # Separado por tabulaciones para scripts
```

## Configuración

Archivo de configuración: `~/.config/icloud-cli/config.toml`

```toml
[general]
default_format = "table"
verbose = false

[auth]
apple_id = "your@icloud.com"

[sync]
sync_interval_minutes = 15

[calendar]
default_calendar = "Personal"

[reminders]
default_reminder_list = "Reminders"
```

## Desarrollo

```bash
# Instala con las dependencias de desarrollo
pip install -e ".[dev]"

# Ejecuta las pruebas
pytest tests/ -v

# Lint
ruff check src/ tests/
```

## ⚠️ Descargo de responsabilidad

Este proyecto utiliza **APIs web no oficiales/privadas de iCloud** a través de la biblioteca
[pyicloud](https://github.com/picklepete/pyicloud). Apple puede cambiar
estas APIs en cualquier momento sin previo aviso, lo cual podría romper la funcionalidad. Esta
herramienta no está afiliada ni respaldada por Apple Inc.

## Licencia

[MIT](LICENSE)
