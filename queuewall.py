#!/usr/bin/env python

import getpass
import os
import platform
import subprocess
import sys
import time

################################ CONFIGURATION #################################
# This directory should contain images that are named the hour (0-23) of the day
# e.g. midnight = 00.jpg, 7AM = 07.jpg, noon = 12.jpg, 5PM = 17.jpg
WALLPAPER_DIR = os.path.expanduser('~') + "/docs/images/wallpapers".replace("/", os.sep)
IMAGE_EXTENSION = ".jpg"

# Choose one of: autodetect, gnome, xfce4, lxde, windows, other
DESKTOP_ENV = "autodetect"

ENABLE_LOGGING = False
############################### END CONFIGURATION ##############################


#################################### Classes ###################################
class Wallpaper(object):
   def __init__(self, name):
      self.name = name
   def setWallpaper(self, path):
      print("Wallpaper: %s" % path)
      
# Wallpaper setter for Linux (and other POSIX) family of operating systems
class LinuxWallpaper(Wallpaper):
   def __init__(self, name):
      ################################ Commands ################################
      # The commands to run for each desktop environment.
      # The first occurrence of %s will be replaced with the path to the image
      self.COMMANDS = { "gnome" : "gconftool-2 --type str --set /desktop/gnome/background/picture_filename %s",
                        # TODO: this only works with xfce >= 4.6.0 and assumes a screen and monitor
                        "xfce4"  : "xfconf-query -c xfce4-desktop -p /backdrop/screen0/monitor0/image-path -s %s",
                        "lxde"  : "pcmanfm --set-wallpaper=%s",
                        "other" : "feh --bg-scale %s" }
      if name == "autodetect":
         self.name = self.detectEnvironment()
      else:
         self.name = name

   def setWallpaper(self, file_path):
      if self.name in self.COMMANDS:
         # lookup the command and replace "%s" with the path to the file
         command = self.COMMANDS[self.name] % file_path
         os.system(command)
         log("Setting wallpaper: " + file_path)
      else:
         log(DESKTOP_ENV + " not in list of known commands")
         exit(1)

   # attempt to detect the desktop environment that the user is running
   def detectEnvironment(self):
      DE_PROCESS_TABLE = { "gnome" : "gnome-session",
                           "xfce"  : "xfce-mcs-manage",
                           "xfce4" : "xfce4-session",
                           "lxde"  : "lxsession" }
      for de in DE_PROCESS_TABLE.keys():
         # use pgrep to see if a process exists under that name
         stat = subprocess.call(["pgrep", "-u", getpass.getuser(), DE_PROCESS_TABLE[de]])
         if stat == 0:
            return de
      return "other"

# Wallpaper setter for Windows family of OSes
class WindowsWallpaper(Wallpaper):
   def __init__(self, name):
      self.name = name
      self.sysroot = os.environ['SYSTEMROOT']
      self.userprofile = os.environ['USERPROFILE'] 

   def setWallpaper(self, file_path):
      if file_path.lower().endswith(".bmp"):
         image_path = file_path
      else:
         # Windows only supports BMP images, so if the image is not BMP,
         # convert it one first
         local_image_path = "Wallpaper1.bmp"
         if os.path.exists(local_image_path):
            log("Deleting: %s" % local_image_path)
            os.unlink(local_image_path)
         # TODO: user ImageMagick's convert to support more formats?
         command = "djpeg -bmp -outfile \"%s\" \"%s\"" % (local_image_path, file_path)
         log("Running: %s" % command)
         os.system(command)
         image_path = self.userprofile + "\\Local Settings\\Application Data\\Microsoft\\Wallpaper1.bmp"
         log("Moving: %s => %s" % (local_image_path, image_path))
         if os.path.exists(image_path):
            log("Deleting: %s" % image_path)
            os.unlink(image_path)
         os.rename(local_image_path, image_path)

      # TODO: stretch, center, or tile?
      command = "REG ADD \"HKCU\\Control Panel\\Desktop\" /V Wallpaper /T REG_SZ /F /D \"%s\"" % image_path
      os.system(command)
      # tell system to update immediately
      os.system(self.sysroot + "\\System32\\RUNDLL32.EXE user32.dll, UpdatePerUserSystemParameters")
      log("Setting wallpaper: " + image_path)

################################### Functions ##################################
# log a message
# TODO: log to a file
def log(inStr):
   if ENABLE_LOGGING:
      print(time.ctime() + ": " + inStr)

# get the current Desktop Environment
def currentDE():
   if DESKTOP_ENV == "autodetect":
      # posix
      if platform.system().lower().startswith("linux"):
         de = LinuxWallpaper(DESKTOP_ENV)
      # windows
      else:
         de = WindowsWallpaper("windows")
      log("autodetected \"" + de.name + "\"")
   else:
      if DESKTOP_ENV == "windows":
         de = WindowsWallpaper("windows")
      else:
         de = LinuxWallpaper(DESKTOP_ENV)

   return de

#################################### main ######################################
if __name__ == "__main__":
   last_hour = -1

   de = currentDE()

   # loop forever, sleeping for 1 minute and checking the new hour
   while(1):
      the_hour = time.localtime().tm_hour
      # if the hour has rolled over
      if last_hour != the_hour:
         wallpaper = WALLPAPER_DIR + os.sep + "%02d" % the_hour + IMAGE_EXTENSION
         if os.path.exists(wallpaper):
            de.setWallpaper(wallpaper)
            last_hour = the_hour
         else:
            log("No wallpaper: " + wallpaper)
            last_hour = -1  # this forces a check next iteration
      time.sleep(60)
