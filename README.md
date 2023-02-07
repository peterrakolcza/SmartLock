# Smart Lock - WIP

<img src="https://freesvg.org/img/1543428916.png" align="right"
     alt="Size Limit logo by Anton Lovchikov" height="290">

A smart lock built using ESP8266, an affordable microcontroller with WiFi capabilities, that can be controlled through a mobile app or web interface.

## Features
* 📱 Remote control of lock through app or web interface
* 🔐 Smart home integration like Homebridge.
* 🕰️ Real-time status updates
* 📈 Event log to track lock activity
* 🔨 Easy installation, compatible with most standard locks

## 🚀 Getting Started
1. Clone the repository to your local machine.
```bash
git clone https://github.com/username/esp8266-smart-lock.git
```
2. Choose the correct 3D models for your lock type

| Screws on the top and bottom   |      Screws on the sides      |
|:----------:|:-------------:|
| <img src="https://pressbooks.bccampus.ca/basicmotorcontrol/wp-content/uploads/sites/887/2020/01/Wiring-Diagram-Pushbutton-1024x764.png" alt="Size Limit logo by Anton Lovchikov" height="290"> |  <img src="https://pressbooks.bccampus.ca/basicmotorcontrol/wp-content/uploads/sites/887/2020/01/Wiring-Diagram-Pushbutton-1024x764.png" alt="Size Limit logo by Anton Lovchikov" height="290"> |

3. 3D print the selected models
4. Connect to components using the [Wiring diagram](#wiring-diagram)
5. Test each component one-by-one
6. Flash the firmware
7. Assemble the whole lock

## Wiring diagram
<img src="https://pressbooks.bccampus.ca/basicmotorcontrol/wp-content/uploads/sites/887/2020/01/Wiring-Diagram-Pushbutton-1024x764.png"
     alt="Size Limit logo by Anton Lovchikov" height="290">

## Homebridge integration

<p align="center">
<img src="https://homekitnews.com/wp-content/uploads/2019/06/UI-SETTINGS-HOME2-IOS13.jpg" alt="Size Limit logo by Anton Lovchikov" height=300>
</p>

Homebridge allows you to integrate with smart home devices that do not natively support HomeKit. There are over 2,000 Homebridge plugins supporting thousands of different smart accessories.

```json
{
  "accessories": [
    {
        "accessory": "EspLock",
        "name": "Front Door",
        "url": "your-custom-or-homegrown-service-url",
		"lock-id": "1",
        "username" : "your-username",
		"password" : "your-password"
    }
  ]
}
```

To disable autolock feature, delete the following function from the index.js file:
```js
setTimeout(function() {
                if (currentState == Characteristic.LockTargetState.UNSECURED) { 
                    self.lockservice
                        .setCharacteristic(Characteristic.LockTargetState, Characteristic.LockTargetState.SECURED);
                }
            }, 5000);
```

## Contributions
🙏 I welcome contributions from the community! If you have any ideas or suggestions, please open an issue or submit a pull request.

## License
This project is licensed under the MIT License. See LICENSE for more information.

## 💻 Contact
For any questions or concerns, please open an issue or contact me.
