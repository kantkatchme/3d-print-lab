# Elegoo CC2: MQTT notes

Working notes on controlling the printer over MQTT instead of letting the Home Assistant integration drive the camera.

## The problem

The `elegoo-homeassistant` integration sends `video_enable=1` over MQTT. On our printer that wedged the camera service. The idea: leave video off, read telemetry and printer-side detections over MQTT, and take camera frames separately.

## Topics we've seen

Treat these as observations, not documentation: names and payloads can change with firmware.

| Topic | Value | Meaning |
|---|---|---|
| `status/device/spaghetti_detection` | on/off | Is the printer's built-in spaghetti detection active? |
| `status/device/foreign_object_detection` | on/off | Is foreign-object detection active? |
| `control/camera/video_enable` | 1/0 | Starts the video service. The one that wedged our stream |
| `control/device/...` | ? | Control topics, still to be mapped |

## To try

1. Record all topics during a print with a monitor (`mosquitto_sub -v -t '#'`)
2. Test `control/device/spaghetti_detection` and `control/device/foreign_object_detection`
3. Make the integration stop sending video-enable (either patch it, or block the message in Home Assistant with an automation)
4. Automation: spaghetti detected -> push with file name and current layer

## Tools

- MQTT client: `brew install mosquitto` (`mosquitto_pub`, `mosquitto_sub`)
- Home Assistant: Developer Tools -> Actions -> `mqtt.publish` for quick experiments

```yaml
mqtt:
  discovery: true
  discovery_prefix: homeassistant
```
