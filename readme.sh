### SETUP ###

#1. move files to rasp
#2. sudo raspi-config > interface options > I2C > enabled
#3. sudo reboot
#4. sudo apt update
#5. sudo apt install python3-venv libportaudio2 libportaudiocpp0 portaudio19-dev
#6. python3 -m venv blinka-env
#7. source ~/blinka-env/bin/activate
#8. pip install adafruit-blinka RPi.GPIO adafruit-circuitpython-ssd1306 numpy sounddevice Pillow