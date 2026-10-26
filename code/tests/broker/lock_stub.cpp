// Host build of the lock firmware's HomeKey bridge, see run.sh
#define HOMEKEY_MODE 1
#define HOMEKEY_TOPIC_PREFIX "smartlock-reader"
#define MQTT_PORT 18830
#define MQTT_USER ""
#define MQTT_PASS ""
#include "../../smart_lock/homekey_bridge.h"
bool locked=true;
void onCmd(bool l){ printf("[lock] COMMAND %s\n", l?"lock":"unlock"); fflush(stdout); locked=l; homekeyReportState(locked); }
int main(){ homekeyBegin(onCmd); homekeyReportState(locked); homekeyReportBattery(87); unsigned long t=millis(); while(millis()-t<40000){ homekeyLoop(); delay(2);} }
