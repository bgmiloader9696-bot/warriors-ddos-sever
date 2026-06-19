from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import time
import os
import threading
import random

app = Flask(__name__)
CORS(app)

MAX_DURATION = 600
ATTACKS = {}
START_TIME = time.time()

# ============================================
# 14 API KEYS WITH SLOTS (HIDDEN)
# ============================================
API_KEYS = {
    "KEY_1_SLOT_1": {"key": "e948ceb29867e38320e4c05a80206176eea84093a8ae0b0ef4657b78430670da", "slots": 1},
    "KEY_2_SLOTS_2": {"key": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6", "slots": 2},
    "KEY_3_SLOTS_3": {"key": "b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7", "slots": 3},
    "KEY_4_SLOTS_4": {"key": "c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8", "slots": 4},
    "KEY_5_SLOTS_5": {"key": "d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9", "slots": 5},
    "KEY_6_SLOTS_6": {"key": "e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0", "slots": 6},
    "KEY_7_SLOTS_7": {"key": "f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1", "slots": 7},
    "KEY_8_SLOTS_8": {"key": "g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2", "slots": 8},
    "KEY_9_SLOTS_9": {"key": "h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2g3", "slots": 9},
    "KEY_10_SLOTS_10": {"key": "i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2g3h4", "slots": 10},
    "KEY_11_SLOTS_11": {"key": "j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2g3h4i5", "slots": 11},
    "KEY_12_SLOTS_12": {"key": "k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2g3h4i5j6", "slots": 12},
    "KEY_13_SLOTS_13": {"key": "l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2g3h4i5j6k7", "slots": 13},
    "KEY_14_SLOTS_14": {"key": "m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2g3h4i5j6k7l8", "slots": 14}
}

# Store active keys
ACTIVE_KEYS = {}

def get_key_info(api_key):
    for key_name, key_data in API_KEYS.items():
        if key_data["key"] == api_key:
            return {
                "name": key_name,
                "slots": key_data["slots"],
                "valid": True
            }
    return {"valid": False}

def get_total_slots():
    total = 0
    for key_name, key_data in API_KEYS.items():
        if key_name in ACTIVE_KEYS and ACTIVE_KEYS[key_name].get("active", False):
            total += key_data["slots"]
    return total

def get_used_slots():
    return len([a for a in ATTACKS.values() if a['status'] == 'running'])

@app.route('/', methods=['GET'])
def home():
    active = get_used_slots()
    total = get_total_slots()
    return jsonify({
        "server_name": "WARRIOR DDOS",
        "server_status": "🟢 ONLINE" if active < total else "🔴 BUSY",
        "total_slots": total,
        "available_slots": total - active,
        "active_attacks": active,
        "total_attacks": len(ATTACKS),
        "version": "2.0",
        "power": "💀 100%"
    })

@app.route('/keys', methods=['GET'])
def list_keys():
    keys_list = []
    for key_name, key_data in API_KEYS.items():
        keys_list.append({
            "name": key_name,
            "slots": key_data["slots"],
            "status": "active" if ACTIVE_KEYS.get(key_name, {}).get("active", False) else "inactive"
        })
    return jsonify({
        "total_keys": len(API_KEYS),
        "active_keys": len([k for k in ACTIVE_KEYS if ACTIVE_KEYS[k].get("active", False)]),
        "keys": keys_list
    })

@app.route('/key/activate', methods=['POST'])
def activate_key():
    try:
        data = request.json
        key_name = data.get('key_name')
        
        if key_name not in API_KEYS:
            return jsonify({"success": False, "error": "Invalid key name"}), 400
        
        ACTIVE_KEYS[key_name] = {
            "active": True,
            "activated_at": time.time()
        }
        
        return jsonify({
            "success": True,
            "message": f"Key {key_name} activated!",
            "slots": API_KEYS[key_name]["slots"]
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/key/deactivate', methods=['POST'])
def deactivate_key():
    try:
        data = request.json
        key_name = data.get('key_name')
        
        if key_name not in API_KEYS:
            return jsonify({"success": False, "error": "Invalid key name"}), 400
        
        if key_name in ACTIVE_KEYS:
            del ACTIVE_KEYS[key_name]
        
        return jsonify({
            "success": True,
            "message": f"Key {key_name} deactivated!"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/attack', methods=['POST'])
def start_attack():
    try:
        data = request.json
        target = data.get('target')
        port = int(data.get('port', 80))
        duration = int(data.get('duration', 60))
        api_key = data.get('key')
        
        key_info = get_key_info(api_key)
        if not key_info["valid"]:
            return jsonify({"success": False, "error": "Invalid API key"}), 401
        
        key_name = key_info["name"]
        max_slots = key_info["slots"]
        
        if key_name not in ACTIVE_KEYS or not ACTIVE_KEYS[key_name].get("active", False):
            return jsonify({
                "success": False,
                "error": "Key not activated!",
                "key_name": key_name
            }), 403
        
        if not target:
            return jsonify({"success": False, "error": "Target required"}), 400
        
        if duration > MAX_DURATION:
            return jsonify({"success": False, "error": f"Duration exceeds max: {MAX_DURATION}s"}), 400
        
        if duration < 5:
            return jsonify({"success": False, "error": "Duration must be at least 5 seconds"}), 400
        
        key_attacks = [a for a in ATTACKS.values() if a.get('key_name') == key_name and a['status'] == 'running']
        if len(key_attacks) >= max_slots:
            return jsonify({
                "success": False,
                "error": f"All {max_slots} slots for this key are busy!",
                "key_name": key_name,
                "max_slots": max_slots,
                "used_slots": len(key_attacks)
            }), 403
        
        attack_id = f"attack_{int(time.time())}"
        
        ATTACKS[attack_id] = {
            "target": target,
            "port": port,
            "duration": duration,
            "started": time.time(),
            "status": "running",
            "key_name": key_name,
            "key_slots": max_slots
        }
        
        active_now = get_used_slots()
        total = get_total_slots()
        
        return jsonify({
            "success": True,
            "message": "Attack started",
            "attack_id": attack_id,
            "target": target,
            "port": port,
            "duration": duration,
            "key_name": key_name,
            "key_slots": max_slots,
            "key_slots_used": len(key_attacks) + 1,
            "key_slots_available": max_slots - (len(key_attacks) + 1),
            "total_slots_used": active_now,
            "total_slots": total,
            "total_slots_available": total - active_now
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/attack/stop', methods=['POST'])
def stop_attack():
    try:
        data = request.json
        attack_id = data.get('attack_id')
        api_key = data.get('key')
        
        key_info = get_key_info(api_key)
        if not key_info["valid"]:
            return jsonify({"success": False, "error": "Invalid API key"}), 401
        
        key_name = key_info["name"]
        
        if attack_id in ATTACKS:
            if ATTACKS[attack_id].get('key_name') != key_name:
                return jsonify({"success": False, "error": "You can only stop your own attacks"}), 403
            
            ATTACKS[attack_id]['status'] = 'stopped'
            
            active_now = get_used_slots()
            total = get_total_slots()
            
            return jsonify({
                "success": True,
                "message": "Attack stopped",
                "attack_id": attack_id,
                "slots_used": active_now,
                "slots_total": total,
                "slots_available": total - active_now
            })
        else:
            return jsonify({"success": False, "error": "Attack not found"}), 404
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/status', methods=['GET'])
def get_status():
    active = get_used_slots()
    total = get_total_slots()
    return jsonify({
        "status": "online",
        "active_attacks": active,
        "total_attacks": len(ATTACKS),
        "total_slots": total,
        "slots_used": active,
        "slots_available": total - active,
        "active_keys": len([k for k in ACTIVE_KEYS if ACTIVE_KEYS[k].get("active", False)]),
        "timestamp": time.time()
    })

@app.route('/slots', methods=['GET'])
def get_slots():
    active = [a for a in ATTACKS.values() if a['status'] == 'running']
    
    # Key wise slots
    key_slots = []
    for key_name, key_data in API_KEYS.items():
        used = len([a for a in ATTACKS.values() if a.get('key_name') == key_name and a['status'] == 'running'])
        key_slots.append({
            "key": key_name,
            "total": key_data["slots"],
            "used": used,
            "available": key_data["slots"] - used,
            "active": ACTIVE_KEYS.get(key_name, {}).get("active", False)
        })
    
    active_list = []
    for a in active:
        elapsed = int(time.time() - a['started'])
        remaining = max(0, a['duration'] - elapsed)
        active_list.append({
            "target": a['target'],
            "port": a['port'],
            "key": a.get('key_name', 'unknown'),
            "elapsed": elapsed,
            "remaining": remaining,
            "duration": a['duration'],
            "status": a['status']
        })
    
    return jsonify({
        "total_slots": get_total_slots(),
        "used": len(active),
        "available": get_total_slots() - len(active),
        "key_wise": key_slots,
        "active_attacks": active_list
    })

@app.route('/health', methods=['GET'])
def health():
    active = get_used_slots()
    total = get_total_slots()
    return jsonify({
        "status": "healthy",
        "server": "WARRIOR DDOS",
        "uptime": f"{int(time.time() - START_TIME)} seconds",
        "active_attacks": active,
        "slots_available": total - active,
        "active_keys": len([k for k in ACTIVE_KEYS if ACTIVE_KEYS[k].get("active", False)]),
        "timestamp": time.time()
    })

@app.route('/info', methods=['GET'])
def info():
    active = get_used_slots()
    total = get_total_slots()
    return jsonify({
        "server": {
            "name": "WARRIOR DDOS",
            "version": "2.0",
            "status": "online",
            "uptime": f"{int(time.time() - START_TIME)} seconds"
        },
        "keys": {
            "total": len(API_KEYS),
            "active": len([k for k in ACTIVE_KEYS if ACTIVE_KEYS[k].get("active", False)]),
            "inactive": len(API_KEYS) - len([k for k in ACTIVE_KEYS if ACTIVE_KEYS[k].get("active", False)])
        },
        "slots": {
            "total": total,
            "used": active,
            "available": total - active
        },
        "attack": {
            "max_duration": f"{MAX_DURATION} seconds",
            "total_attacks": len(ATTACKS),
            "threads_per_attack": 25
        },
        "timestamp": time.time()
    })

@app.route('/auto_complete', methods=['POST'])
def auto_complete():
    try:
        current_time = time.time()
        for attack_id, attack in list(ATTACKS.items()):
            if attack['status'] == 'running':
                elapsed = current_time - attack['started']
                if elapsed >= attack['duration']:
                    attack['status'] = 'completed'
                    print(f"✅ Attack completed: {attack_id}")
        
        for attack_id, attack in list(ATTACKS.items()):
            if attack['status'] in ['completed', 'stopped']:
                if current_time - attack['started'] > 300:
                    del ATTACKS[attack_id]
                    print(f"🧹 Cleaned up: {attack_id}")
        
        return jsonify({"success": True, "message": "Auto complete ran"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    print("="*60)
    print("🔥 WARRIOR DDOS API - 14 KEYS SYSTEM")
    print("="*60)
    print(f"📡 Server: http://0.0.0.0:{port}")
    print(f"🔑 Total Keys: {len(API_KEYS)}")
    print(f"📌 Total Slots: {sum([k['slots'] for k in API_KEYS.values()])}")
    print("="*60)
    app.run(host='0.0.0.0', port=port, debug=False)