# Emulates the HomeKey-ESP32 reader's MQTT behaviour against the lock's built-in broker
import time, paho.mqtt.client as mqtt
P="smartlock-reader"
got=[]
def on_msg(c,u,m): got.append((m.topic,m.payload.decode(),m.retain)); print("[reader] got",m.topic,m.payload.decode(),"retain" if m.retain else "")
def client():
    c=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=P, protocol=mqtt.MQTTv311)
    c.on_message=on_msg
    c.will_set(P+"/status","offline",qos=1,retain=True)
    c.connect("127.0.0.1",18830,keepalive=5); c.loop_start(); time.sleep(0.3)
    c.publish(P+"/status","online",qos=1,retain=True)
    for t in ["set_state","set_current_state","set_target_state","set_battery_lvl"]: c.subscribe(P+"/homekit/"+t,0)
    time.sleep(0.5); return c
c=client()
assert (P+"/homekit/set_state","1",True) in got and (P+"/homekit/set_battery_lvl","87",True) in got, got
got.clear()
c.publish(P+"/homekit/state","4",qos=1,retain=True); time.sleep(0.5)   # HomeKey tap -> unlocking
assert (P+"/homekit/set_state","0",False) in got, got
got.clear()
c.publish(P+"/homekit/state","0",qos=0,retain=True); time.sleep(0.3)   # settled echo, must be ignored
assert not got, got
c.publish(P+"/homekit/state","5",qos=0,retain=True); time.sleep(0.5)   # Home app -> locking
assert (P+"/homekit/set_state","1",False) in got, got
c.publish("x"*200, "y"*3000, qos=1); time.sleep(0.5)                 # oversized discovery-style packet
time.sleep(6)                                                          # keepalive pings
assert c.is_connected(), "dropped during keepalive"
c.disconnect(); c.loop_stop(); got.clear()
c=client()                                                             # reconnect after reboot
assert (P+"/homekit/set_state","1",True) in got and (P+"/homekit/set_battery_lvl","87",True) in got, got
print("ALL OK")
