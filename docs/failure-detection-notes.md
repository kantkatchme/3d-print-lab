# Failure detection: how we got here

Notes from building the print guard on an Elegoo Centauri Carbon 2 (CC2). Mostly a list of what worked, what didn't, and why the final design looks the way it does.

## Why bother

The worst failure so far: a print came loose from the plate and got dragged around by the toolhead until it jammed the nozzle. Nobody noticed for hours. Most failed prints fail **in the first layers** (adhesion), so that's where checks matter most, and why the guard checks more often during layers 1-5.

## Three ideas, ranked

1. **Camera watchdog** (`cam_watch.py`). Any AI is blind without a picture, so first make sure the picture exists. The CC2 serves MJPEG on port 8080 (`http://<printer>:8080/mjpeg`). Healthy stream = a frame within a few seconds. Dead = connection reset or nothing.
2. **LLM vision check** (`guard.py`, what we ended up with). Frame + print context -> Claude -> GREEN/YELLOW/RED. No training data, no GPU, and it understands *context* ("at layer 40 of 120 there should be a part this tall").
3. **Local detector** such as [pycentauri](https://github.com/tholterhus/pycentauri) (an object detector trained on spaghetti). Free to run and fast, but it only knows spaghetti: no detached parts, no layer shifts, no warping. Worth trying alongside, not instead.

Obico, the well-known failure detector, works with OctoPrint, Klipper and Bambu printers, not the CC2.

## What the LLM guard does well and badly

- **Good at:** obvious spaghetti, an empty bed in the middle of a print, a part that tipped over, blobs on the nozzle. The implausible-height check ("30 % done but nothing on the plate") is cheap and reliable.
- **Weak at:** a dark wide-angle chamber image, a nozzle that hides the part, many small objects. The prompt says so explicitly. Without that, it cries wolf.
- **So it's conservative by design:** RED only for a clear finding, two REDs in a row before alerting, a stronger model gets the second opinion, and auto-pause is opt-in.
- **Cost:** about 15 checks per print hour with the small model. Tokens and USD are logged for every verdict.

## The camera problem (CC2)

The built-in camera service can hang: port 8080 stops delivering frames until the printer is power-cycled. In our case it turned out to be a hardware fault in some CC2 batches (see the [Elegoo issue](https://github.com/elegooofficial/CentauriCarbon2/issues/13)), and the unit went back for replacement.

What we learned along the way:

- The Home Assistant integration sends a `video_enable` command that can wedge the stream service. If your camera dies right after Home Assistant starts talking to the printer, look there first. See [mqtt-notes.md](mqtt-notes.md).
- There is no way to restart the camera service without root on the printer. Don't go there, you'll void the warranty.
- Fallbacks if the built-in camera keeps failing: a USB endoscope camera or an ESP32-CAM pointed into the chamber, served as MJPEG on the same URL, will work with the guard unchanged.
- The printer itself has **built-in spaghetti and foreign-object detection** with auto-pause. It works without the video stream. Turn it on first, then add the guard as a second pair of eyes.

## What happens on an alert

1. Notification (red/yellow) with the file name and layer
2. The frame is saved in the alarm folder, so you can later check what the model actually saw
3. Optional: text-to-speech in the house, and a second message for housemates without file names
4. Optional: pause the print (only if you created the `autopause` flag)

## Practical tips that need no software

- Clean the plate with isopropanol before every print and watch the first layer.
- Dry your filament if you see stringing or blobs.
- Leave the chamber light on, or the camera sees nothing.
- Run long prints overnight only with the guard active.
