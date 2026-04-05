# PCB.AI — Usage Guide

PCB.AI is a desktop application that uses Claude as an AI co-designer to help you build production-ready PCBs through a conversation. You describe what you want to build; the AI handles component selection, layout guidance, simulation checks, and export.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.10+ | `python3 --version` |
| Node.js 18+ | `node --version` |
| KiCad 7 or 8 | Must be installed so pcbnew is importable |
| Anthropic API key | From [console.anthropic.com](https://console.anthropic.com) |

---

## Installation

```bash
# 1. Clone the repo
git clone <repo-url>
cd secrety

# 2. Install Node dependencies (root + frontend)
npm run install:all

# 3. Install Python dependencies
npm run install:python
# equivalent to: pip3 install -r pcbai/backend/requirements.txt

# 4. Create your environment file
cp .env.example .env
# Then open .env and set:
#   ANTHROPIC_API_KEY=sk-ant-...
#   BACKEND_PORT=7842  (default, change only if port is taken)
```

---

## Running

```bash
npm run dev
```

This starts three processes simultaneously:
- **BACKEND** — FastAPI on `localhost:7842`
- **VITE** — React dev server on `localhost:5173`
- **ELECTRON** — Desktop window (waits for Vite to be ready first)

The Electron window opens automatically. Closing the window kills all three processes — no orphaned Python processes.

---

## The Interface

The window is split into four panels:

```
┌─────────────────┬──────────────────────────────┐
│                 │      Board Preview            │
│   Chat Panel    ├──────────────────────────────┤
│   (left 1/3)   │      Component List           │
│                 ├───────────────┬──────────────┤
│                 │  Simulation   │   Export     │
└─────────────────┴───────────────┴──────────────┘
```

- **Chat** — your main interface. Type here to talk to the AI.
- **Board Preview** — live KiCad board view (updates as the AI places components).
- **Component List** — shows all components on the board with their values.
- **Simulation / Export** — run electrical checks and generate fabrication files.

---

## Designing a Board

### Step 1 — Describe your project

Just tell the AI what you want to build, the same way you'd explain it to a colleague:

> "I want to build a USB-C powered LED driver that dims 4 LEDs independently using PWM. It should run from 5V and be hand-soldered."

The AI adapts its language to your level automatically. It picks up on technical vocabulary ("QFN", "IPC-2221", "buck converter") to gauge how much detail to use. If you're a beginner, it explains its choices in plain English.

### Step 2 — Answer clarifying questions

The AI will ask questions it needs to make good decisions:

- Assembly method (hand soldering, reflow, pick-and-place)?
- Target board size?
- Power budget constraints?
- Any specific ICs you want to use?

You don't have to answer all questions at once. Just give what you know.

### Step 3 — Upload datasheets (optional)

If you're using a specific chip, drag and drop its PDF datasheet onto the chat window (or use the upload button). The AI extracts:

- Pin counts and functions
- Decoupling capacitor requirements
- Layout-critical notes (thermal pads, keepout zones)
- Absolute maximum ratings
- Operating voltage and current specs

It cites constraints from the datasheet directly in its responses.

### Step 4 — Review component choices

The AI resolves component descriptions to specific KiCad footprints. For example:

> "100nF decoupling cap" → `Capacitor_SMD:C_0402_1005Metric`, value `100n`

If a component is ambiguous, the AI asks rather than guesses. You can override any choice by just saying so:

> "Use 0805 resistors instead — I prefer them for hand soldering."

### Step 5 — Let the AI lay out the board

Once components are agreed on, the AI works with KiCad directly to:
1. Place components with sensible default positions
2. Route power and ground planes
3. Add signal traces
4. Run DRC (Design Rule Check) and fix violations automatically (up to 10 iterations)

You can intervene at any point:

> "Move R3 closer to U1" or "Put all the connectors along the left edge"

### Step 6 — Run simulations

The AI runs electrical checks before routing:

**Power budget** — confirms your regulator has enough headroom:
```
Total load: 340 mA
Regulator capacity: 500 mA
Margin: 32% ✓
```

**Trace width** (IPC-2221) — flags any trace too narrow for its current:
```
Net PWR_5V: 1.0 mm actual, 0.45 mm minimum for 1.8A ✓
Net LED_DRV: 0.1 mm actual, 0.27 mm minimum for 1.0A ✗
```

**Impedance** — checks controlled-impedance and differential pair traces:
```
USB_DP (differential): 91.2 Ω calculated vs 90 Ω target (1.3% error) ✓
```

**SPICE netlist** — generates a simulation file you can open in LTspice:
```
POST /simulation/spice
{ "circuit_type": "buck", "components": [...] }
```

### Step 7 — Export

When the board looks good, export fabrication files:

> "Export for JLCPCB"

The AI packages:
- Gerber files (copper layers, silkscreen, solder mask, drill)
- Drill file (Excellon format)
- Bill of Materials (CSV)
- Pick-and-place / CPL file

Files land in the directory you specify (or the project folder by default).

---

## Conversation Tips

**Be specific about constraints:**
> "Under $5 BOM cost at 100 units" is more useful than "cheap"

**Reference previous decisions:**
> "Keep the same package family we decided on earlier"

**Ask for explanations:**
> "Why did you choose that inductor value?"

**Correct mistakes directly:**
> "That bypass cap should be 10µF, not 100µF"

**Ask what-if questions:**
> "What happens to efficiency if I increase the switching frequency to 1MHz?"

The AI remembers everything in the conversation. You don't need to repeat context.

---

## Backend API (for scripting / integration)

The backend is a plain HTTP API running on `localhost:7842`. You can call it directly from scripts or other tools.

### Health check
```bash
curl http://localhost:7842/health
# {"status": "ok", "version": "0.3.0"}
```

### Chat (streaming)
```bash
curl -X POST http://localhost:7842/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "I want to build a 5V LDO regulator circuit", "session_id": "my-session"}' \
  --no-buffer
```

Response is a stream of Server-Sent Events:
```
data: {"type": "text", "text": "Let's design that LDO circuit. "}
data: {"type": "text", "text": "For a 5V output you'd typically..."}
data: {"type": "meta", "expertise_level": "unknown", "stage": "intent_capture", "session_id": "my-session"}
data: {"type": "done"}
```

### Component resolution
```bash
curl -X POST http://localhost:7842/component/resolve \
  -H "Content-Type: application/json" \
  -d '{
    "descriptions": ["100nF bypass cap", "10k pull-up resistor"],
    "assembly_method": "hand",
    "expertise_level": "beginner"
  }'
```

Response:
```json
{
  "resolved": [
    {
      "description": "100nF bypass cap",
      "type": "capacitor",
      "value": "100n",
      "package": "0805",
      "footprint_id": "Capacitor_SMD:C_0805_2012Metric",
      "reasoning": "0805 chosen for hand soldering ease"
    }
  ],
  "needs_clarification": [],
  "all_resolved": true
}
```

### Datasheet upload
```bash
curl -X POST http://localhost:7842/datasheet/upload \
  -F "file=@AMS1117.pdf" \
  -F "session_id=my-session"
```

### Simulation checks
```bash
curl -X POST http://localhost:7842/simulation/run \
  -H "Content-Type: application/json" \
  -d '{
    "components": [
      {"ref": "U1", "type": "ldo", "capacity_ma": 800},
      {"ref": "U2", "type": "mcu", "current_ma": 150, "voltage_v": 3.3},
      {"ref": "LED1", "type": "led", "current_ma": 20, "voltage_v": 3.3}
    ],
    "nets": [
      {"name": "PWR_3V3", "current_a": 0.17, "width_mm": 0.5, "layer": "F.Cu"}
    ]
  }'
```

### SPICE netlist generation
```bash
curl -X POST http://localhost:7842/simulation/spice \
  -H "Content-Type: application/json" \
  -d '{
    "circuit_type": "ldo",
    "components": [
      {"ref": "U1", "type": "ldo", "vin": 5.0, "vout": 3.3},
      {"ref": "C1", "type": "capacitor", "value": "10u"},
      {"ref": "RL", "type": "resistor", "value": "100"}
    ],
    "nets": []
  }'
```

Supported `circuit_type` values: `ldo`, `buck`, `boost`, `rc_filter`, `lc_filter`, `diff_amp`

### KiCad control
```bash
# Connect to KiCad and open/create a board
curl -X POST http://localhost:7842/kicad/connect \
  -H "Content-Type: application/json" \
  -d '{"board_path": "/tmp/myboard.kicad_pcb", "width_mm": 80, "height_mm": 60}'

# Place a component
curl -X POST http://localhost:7842/kicad/component/place \
  -H "Content-Type: application/json" \
  -d '{
    "footprint_id": "Resistor_SMD:R_0805_2012Metric",
    "ref": "R1", "value": "10k",
    "x_mm": 40, "y_mm": 30
  }'

# Run DRC
curl -X POST http://localhost:7842/kicad/drc

# Export files
curl -X POST http://localhost:7842/export \
  -H "Content-Type: application/json" \
  -d '{"output_dir": "/tmp/gerbers", "formats": ["gerbers", "drill", "bom", "pnp"]}'
```

### Session management
```bash
# Get session info (expertise level, current stage, message count)
curl http://localhost:7842/chat/session/my-session

# Reset a session
curl -X POST http://localhost:7842/chat/reset \
  -H "Content-Type: application/json" \
  -d '{"session_id": "my-session"}'
```

---

## Running Tests

```bash
cd pcbai/backend
python -m pytest tests/ -v
```

131 tests covering:
- Expertise detector (28 tests) — heuristic classification of user messages
- Datasheet parser (33 tests) — PDF extraction and constraint parsing
- Simulation engine (70 tests) — power budget, trace width, impedance, SPICE generation

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(required)* | Your Anthropic API key |
| `BACKEND_PORT` | `7842` | Port the FastAPI server listens on |
| `ELECTRON_DEV` | unset | Set to `1` to load from Vite dev server instead of built dist |

Without `ANTHROPIC_API_KEY`, the app still runs — the chat endpoint returns a stub response explaining the key is missing, so you can test the UI and API without a key.

---

## KiCad Setup

The app controls KiCad via its Python scripting API (`pcbnew`). KiCad does **not** need to be open — the app drives it headlessly in the background.

### Windows

1. Install KiCad from [kicad.org](https://www.kicad.org/download/) (version 7, 8, or 9)
2. The app auto-detects KiCad under `C:\Program Files\KiCad\`. If your install is elsewhere, set:
   ```powershell
   # In your .env file:
   KICAD_SCRIPTING_DIR=C:\path\to\kicad\bin
   ```
3. Verify detection worked — when the app starts you should see in the `[BACKEND]` log:
   ```
   INFO pcbai.kicad_mcp_client: MCP server subprocess started
   ```
   If you see `pcbnew not found`, check the path above.

4. To verify manually:
   ```powershell
   & "C:\Program Files\KiCad\8.0\bin\python.exe" -c "import pcbnew; print(pcbnew.Version())"
   ```

### macOS
```bash
export PYTHONPATH="/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/lib/python3.11/site-packages"
```

### Linux
```bash
python3 -c "import pcbnew; print(pcbnew.Version())"
# If this fails:
sudo apt install kicad  # or your distro equivalent
```

### Starting a board in the app

Just tell the AI what you want to build. When it reaches the layout stage it will automatically create a new `.kicad_pcb` file in your home directory (`~/pcbai_boards/`) and start placing components. You can also explicitly say:

> "Create a new 80×60mm board at ~/myproject/board.kicad_pcb"

or open an existing board:

> "Open ~/myproject/existing.kicad_pcb"

---

## Troubleshooting

**"Failed to start KiCad MCP server"**
KiCad is not installed or `pcbnew` can't be found. See KiCad Setup above. On Windows, try setting `KICAD_SCRIPTING_DIR` in your `.env` file.

**Electron window is blank**
Vite dev server takes a few seconds to start. The Electron process waits via `wait-on`, but if it times out, run `npm run dev:vite` separately first, then `npm run dev:electron`.

**Backend not responding**
Check the BACKEND terminal (blue) in your terminal for Python errors. Common cause: missing Python package. Run `npm run install:python` again.

**Chat returns stub responses**
`ANTHROPIC_API_KEY` is not set or is set to an empty string in your `.env`. Make sure the file has no extra spaces or quotes around the key value.
