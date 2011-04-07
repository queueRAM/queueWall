#!/usr/bin/env python

import getpass
import optparse
import os
import platform
import select
import subprocess
import sys
import threading
import time

##################### DEFAULT CONFIGURATION #################################
# This directory should contain images that are named the hour (0-23) of the day
# e.g. midnight = 00.jpg, 7AM = 07.jpg, noon = 12.jpg, 5PM = 17.jpg
DEFAULT_WALLPAPER_DIR = os.path.expanduser('~') + "/docs/images/wallpapers".replace("/", os.sep)

DEFAULT_IMAGE_EXTENSION = "jpg"

########################### END DEFAULT CONFIGURATION #######################


#################################### Classes ###################################
class DesktopEnvironment(object):
   def __init__(self, name):
      self.name = name
   def setCommand(self, command):
      self.command = command
   def setWallpaper(self, path):
      print("Wallpaper: %s" % path)
      
# Wallpaper setter for Linux (and other POSIX) family of operating systems
class LinuxDE(DesktopEnvironment):
   def __init__(self, name):
      self.command = None
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
      # lookup the command and replace "%s" with the path to the file
      if (self.command != None):
         command = self.command % file_path
      else:
         # no custom command set, lookup command in dictionary
         if self.name in self.COMMANDS:
            command = self.COMMANDS[self.name] % file_path
         else:
            log(self.name + " not in list of known commands")
            sys.exit(1)
      os.system(command)
      log("Setting wallpaper: " + file_path)

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
class WindowsDE(DesktopEnvironment):
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
      # stretch to fit
      command = "REG ADD \"HKCU\\Control Panel\\Desktop\" /V WallpaperStyle /T REG_SZ /F /D 2"
      os.system(command)
      # tell system to update immediately
      os.system(self.sysroot + "\\System32\\RUNDLL32.EXE user32.dll, UpdatePerUserSystemParameters")
      log("Setting wallpaper: " + image_path)

################################### Functions ##################################
# log a message
# TODO: log to a file
def logInit(enable):
   global enableLogging
   enableLogging = enable

def log(inStr):
   if enableLogging:
      print(time.ctime() + ": " + inStr)

# get the current Desktop Environment
def currentDE(name):
   if name == "autodetect":
      # posix
      if platform.system().lower().startswith("linux"):
         de = LinuxDE(name)
      # assume windows
      else:
         de = WindowsDE("windows")
      log("autodetected \"" + de.name + "\"")
   else:
      if name == "windows":
         de = WindowsDE("windows")
      else:
         de = LinuxDE(name)

   return de

def changeWallpaper(options, de, ev):
   cur_time = time.localtime()
   imagename = "%02d" % cur_time.tm_hour + "." + options.extension
   # if the hour has rolled over, or first time through
   wallpaper = options.directory + os.sep + imagename
   if os.path.exists(wallpaper):
      de.setWallpaper(wallpaper)
   else:
      log("No wallpaper: " + wallpaper)
   # signal the event so the main thread knows this has completed
   log("change: setting")
   ev.set()

# command line input thread
class CommandLineThread(threading.Thread):
   def __init__(self, in_ev, out_ev, fifo):
      self.in_ev = in_ev
      self.out_ev = out_ev
      self.fifo = fifo
      threading.Thread.__init__(self)

   def run(self):
      command = ""
      sys.stdout.write("queueWall> ")
      sys.stdout.flush()
      timeout = 1
      while(command != "exit"):
         rlist, _, _ = select.select([sys.stdin], [], [], timeout)
         if rlist:
            command = sys.stdin.readline().strip()
            if(command == "help"):
               print("Commands: exit, help, restart")
            elif(command == "restart") or (command == "exit"):
               self.fifo.append(command)
               self.out_ev.set()
            else:
               print("Unknown command: %s" % command)
            sys.stdout.write("queueWall> ")
            sys.stdout.flush()
         elif self.in_ev.isSet():
            command = "exit"
      print("")
      log("CommandLine returning...")

#################################### main ######################################
if __name__ == "__main__":
   parser = optparse.OptionParser(usage="%prog [options]", \
                                  version="%prog 0.00")
   parser.add_option("-c", "--command", help="custom command to change wallpaper [example: \"feh --bg-scale %s\"]")
   parser.add_option("-d", "--directory", help="wallpapers directory [default: %default]", \
                     default=DEFAULT_WALLPAPER_DIR)
   parser.add_option("-e", "--extension", help="image extension [default: %default]", \
                     default=DEFAULT_IMAGE_EXTENSION)
   parser.add_option("-l", "--log", action="store_true", \
                     help="enable logging", default=False)
   parser.add_option("-s", "--system", help="currently running system: autodetect, gnome, xfce4, lxde, windows [default: %default]", \
                     default="autodetect")
   parser.add_option("-t", "--terminal", action="store_true", \
                     help="allow commands to be entered from terminal", default=False)

   (options, args) = parser.parse_args()

   logInit(options.log)

   de = currentDE(options.system)
   if options.command != None:
      log("Using command: %s" % options.command)
      de.setCommand(options.command)

   # event flag to wait until thread completes
   command_ev = threading.Event()
   de_ev = threading.Event()

   # call first time through to ensure background for current time is set
   changeWallpaper(options, de, de_ev)

   # spawn command line thread
   if options.terminal:
      fifo = []
      command_thread = CommandLineThread(command_ev, de_ev, fifo).start()

   running = True
   try:
      while running:
         # clear event so it can be used again next time
         de_ev.clear()
         # sleep until the next hour rollover
         cur_time = time.localtime()
         # TODO: this is where the scheduler would figure out the delay
         delay_time = 60 * (60 - cur_time.tm_min) - cur_time.tm_sec
         t = threading.Timer(delay_time, changeWallpaper, [options, de, de_ev])
         log("main: delay time: %d (s)" % delay_time)
         t.start()
         # wait until thread runs and signals its completion
         log("main: waiting")
         de_ev.wait()
         log("main: done waiting")
         if options.terminal and (len(fifo)) > 0:
            command = fifo.pop()
            if(command == "exit"):
               log("main: exiting...")
               t.cancel()
               running = False
            elif(command == "restart"):
               log("main: restarting...")
               t.cancel()
            elif(command != ""):
               log("main: command: %s" % command)
   except KeyboardInterrupt:
      command_ev.set()
      print("Handling KeyboardInterrupt.  Exiting...")
      # Cancel the pending thread.  This can be called even if it has already started.
      t.cancel()

