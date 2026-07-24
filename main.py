import asyncio
import os
import random
import struct
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusServerContext
from pymodbus.server import StartAsyncTcpServer

app = FastAPI()

# Auto Simulation Toggle State
auto_sim_active = False

# 6 Transformers State Storage (ATZ2000E Meters Initial Values)
transformers_data = {
    1: {"v": 6600.0, "a": 132.0, "kw": 845.0, "pf": 0.98, "hz": 50.0},
    2: {"v": 440.0, "a": 185.0, "kw": 178.0, "pf": 0.97, "hz": 50.0},
    3: {"v": 440.0, "a": 106.0, "kw": 195.0, "pf": 0.96, "hz": 50.0},
    4: {"v": 440.0, "a": 246.0, "kw": 986.0, "pf": 0.98, "hz": 50.0},
    5: {"v": 440.0, "a": 106.0, "kw": 195.0, "pf": 0.96, "hz": 50.0},
    6: {"v": 800.0, "a": 6840.0, "kw": 5492.0, "pf": 1.00, "hz": 50.0},
}


def float_to_registers(value):
    """32-bit IEEE 754 Float to 2x 16-bit Modbus Registers Conversion"""
    packed = struct.pack(">f", float(value))
    return struct.unpack(">HH", packed)


async def modbus_updater(context):
    """Sync Modbus Registers and Auto-Simulation Loop"""
    global auto_sim_active
    while True:
        await asyncio.sleep(0.5)

        for t_id in range(1, 7):
            d = transformers_data[t_id]

            if auto_sim_active:
                d["v"] = round(max(0, d["v"] + random.uniform(-2.0, 2.0)), 1)
                d["a"] = round(max(0, d["a"] + random.uniform(-1.5, 1.5)), 1)
                d["pf"] = round(
                    min(1.0, max(0.5, d["pf"] + random.uniform(-0.01, 0.01))), 2
                )
                d["hz"] = round(
                    min(52.0, max(48.0, d["hz"] + random.uniform(-0.02, 0.02))), 2
                )
                d["kw"] = round((d["v"] * d["a"] * d["pf"] * 1.732) / 1000.0, 1)

            # Modbus Register Mapping (Input Registers FC 04 - ATZ2000 Protocol)
            slave = context[t_id]
            slave.setValues(4, 1, float_to_registers(d["v"]))  # 30001: Voltage
            slave.setValues(4, 9, float_to_registers(d["a"]))  # 30009: Current
            slave.setValues(
                4, 19, float_to_registers(d["kw"])
            )  # 30019: Active Power
            slave.setValues(
                4, 43, float_to_registers(d["pf"])
            )  # 30043: Power Factor
            slave.setValues(4, 71, float_to_registers(d["hz"]))  # 30071: Frequency


# --- 🎛️ MEMA2026E MICROTRADE CONTROLLER UI ---
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>MEMA2026E MicroTrade Online Simulator</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-900 text-slate-100 p-6 font-sans">
        <div class="flex flex-col md:flex-row justify-between items-center mb-6 pb-4 border-b border-slate-700 gap-4">
            <div>
                <h1 class="text-2xl font-bold text-sky-400">MEMA2026E MicroTrade Automation Engineering</h1>
                <p class="text-xs text-slate-400">Modbus TCP Stream Port: 5021 | Unit IDs: 1 to 6 (ATZ2000 Output Protocol)</p>
            </div>
            
            <button id="autoBtn" onclick="toggleAuto()" class="px-6 py-3 rounded-lg font-bold text-white transition bg-emerald-600 hover:bg-emerald-500 shadow-lg">
                ⚡ Enable Auto-Simulation (All 6 TFs)
            </button>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6" id="cards"></div>

        <script>
            let autoActive = false;

            async function fetchState() {
                const res = await fetch('/api/state');
                const data = await res.json();
                autoActive = data.auto_sim;
                updateAutoBtnUI();
                renderCards(data.transformers);
            }

            function updateAutoBtnUI() {
                const btn = document.getElementById('autoBtn');
                if (autoActive) {
                    btn.innerText = '🛑 Stop Auto-Simulation';
                    btn.className = 'px-6 py-3 rounded-lg font-bold text-white transition bg-rose-600 hover:bg-rose-500 shadow-lg animate-pulse';
                } else {
                    btn.innerText = '⚡ Enable Auto-Simulation (All 6 TFs)';
                    btn.className = 'px-6 py-3 rounded-lg font-bold text-white transition bg-emerald-600 hover:bg-emerald-500 shadow-lg';
                }
            }

            async function toggleAuto() {
                autoActive = !autoActive;
                await fetch('/api/auto', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({active: autoActive})
                });
                updateAutoBtnUI();
            }

            async function updateParam(id, param, val) {
                document.getElementById(`${param}_val_${id}`).innerText = val;
                await fetch('/api/update', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({id: id, param: param, value: parseFloat(val)})
                });
            }

            function renderCards(tData) {
                const container = document.getElementById('cards');
                let html = '';
                for (let i = 1; i <= 6; i++) {
                    const d = tData[i];
                    html += `
                        <div class="bg-slate-800 p-5 rounded-xl border border-slate-700 shadow-md space-y-3">
                            <div class="flex justify-between items-center border-b border-slate-700 pb-2">
                                <h2 class="font-bold text-lg text-emerald-400">Transformer T${i}</h2>
                                <span class="text-xs font-mono text-amber-400">kW: <span id="kw_val_${i}">${d.kw}</span></span>
                            </div>
                            
                            <div>
                                <div class="flex justify-between text-xs text-slate-300 mb-1">
                                    <span>Voltage (V)</span>
                                    <span class="font-mono text-sky-400" id="v_val_${i}">${d.v}</span>
                                </div>
                                <input type="range" min="0" max="10000" step="5" value="${d.v}" class="w-full accent-sky-500" oninput="updateParam(${i}, 'v', this.value)">
                            </div>

                            <div>
                                <div class="flex justify-between text-xs text-slate-300 mb-1">
                                    <span>Current (A)</span>
                                    <span class="font-mono text-sky-400" id="a_val_${i}">${d.a}</span>
                                </div>
                                <input type="range" min="0" max="7000" step="1" value="${d.a}" class="w-full accent-sky-500" oninput="updateParam(${i}, 'a', this.value)">
                            </div>

                            <div>
                                <div class="flex justify-between text-xs text-slate-300 mb-1">
                                    <span>Power Factor (PF)</span>
                                    <span class="font-mono text-sky-400" id="pf_val_${i}">${d.pf}</span>
                                </div>
                                <input type="range" min="0.5" max="1.0" step="0.01" value="${d.pf}" class="w-full accent-sky-500" oninput="updateParam(${i}, 'pf', this.value)">
                            </div>

                            <div>
                                <div class="flex justify-between text-xs text-slate-300 mb-1">
                                    <span>Frequency (Hz)</span>
                                    <span class="font-mono text-sky-400" id="hz_val_${i}">${d.hz}</span>
                                </div>
                                <input type="range" min="45.0" max="55.0" step="0.05" value="${d.hz}" class="w-full accent-sky-500" oninput="updateParam(${i}, 'hz', this.value)">
                            </div>
                        </div>
                    `;
                }
                container.innerHTML = html;
            }

            setInterval(async () => {
                if (autoActive) {
                    const res = await fetch('/api/state');
                    const data = await res.json();
                    renderCards(data.transformers);
                }
            }, 1000);

            fetchState();
        </script>
    </body>
    </html>
    """


# --- 📡 FASTAPI ENDPOINTS ---
@app.get("/api/state")
async def get_state():
    return {"auto_sim": auto_sim_active, "transformers": transformers_data}


@app.post("/api/auto")
async def toggle_auto(req: Request):
    global auto_sim_active
    body = await req.json()
    auto_sim_active = body["active"]
    return {"status": "success", "auto_sim": auto_sim_active}


@app.post("/api/update")
async def update_val(req: Request):
    body = await req.json()
    t_id = body["id"]
    param = body["param"]
    val = body["value"]
    transformers_data[t_id][param] = val
    d = transformers_data[t_id]
    d["kw"] = round((d["v"] * d["a"] * d["pf"] * 1.732) / 1000.0, 1)
    return {"status": "success"}


@app.on_event("startup")
async def start_services():
    slaves_dict = {}
    for slave_id in range(1, 7):
        block = ModbusSequentialDataBlock(1, [0] * 100)
        slaves_dict[slave_id] = ModbusServerContext(slaves=block)

    context = ModbusServerContext(slaves=slaves_dict, single=False)

    asyncio.create_task(modbus_updater(context))
    asyncio.create_task(StartAsyncTcpServer(context, address=("0.0.0.0", 5021)))