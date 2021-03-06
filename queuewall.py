#!/usr/bin/env python

import getpass
import optparse # TODO: deprecated since 2.7 - use argparse (new in 2.7).
import os
import platform
import random
import select
import subprocess
import sys
import threading
import time
import tempfile

# python devs decided to rename some modules because it looks pretty
if sys.version_info < (3, 0):
   import ConfigParser
   configparser = ConfigParser
else:
   import configparser

##################### DEFAULT CONFIGURATION #################################
# This directory should contain images that are named the hour (0-23) of the day
# e.g. midnight = 00.jpg, 7AM = 07.jpg, noon = 12.jpg, 5PM = 17.jpg
DEFAULT_WALLPAPER_DIR = os.path.join(os.path.expanduser('~'), "docs", "images", "wallpapers")

# image extension to use for time-based schedules
# TODO: this shouldn't be needed.  find a way to avoid it
DEFAULT_IMAGE_EXTENSION = "jpg"

# interval between image changes (in minutes)
DEFAULT_INTERVAL = 60

# scheduler types: hourly, daily, imagename, custom
# TODO: currently unsupported
DEFAULT_SCHEDULE = "hourly"

# default temporary directory to work convert images in
DEFAULT_TEMP_DIR = "None"
########################### END DEFAULT CONFIGURATION #######################

# Instantiate the Config File Parser
queuewall_config = configparser.RawConfigParser()

# set the default configuration
queuewall_config.add_section("Configuration")
queuewall_config.add_section("Directories")
queuewall_config.add_section("Schedule")

# main configuration
queuewall_config.set("Configuration", "caption",  "False")
queuewall_config.set("Configuration", "command",  "")
queuewall_config.set("Configuration", "log",      "False")
queuewall_config.set("Configuration", "random",   "False")
queuewall_config.set("Configuration", "system",   "autodetect")
queuewall_config.set("Configuration", "terminal", "False")
queuewall_config.set("Configuration", "temp_dir", DEFAULT_TEMP_DIR)

# directory options
queuewall_config.set("Directories", "wallpaper_dirs",  DEFAULT_WALLPAPER_DIR)
queuewall_config.set("Directories", "image_extension", DEFAULT_IMAGE_EXTENSION)

# scheduler options
queuewall_config.set("Schedule", "interval",   DEFAULT_INTERVAL)
queuewall_config.set("Schedule", "sched_type", DEFAULT_SCHEDULE)

queuewall_config_file = os.path.join(os.path.expanduser('~'), 
                                     ".config", "queueWall", "config.rc")
queuewall_config.read(queuewall_config_file)

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
         # TODO: use ImageMagick's convert to support more formats?
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
      command = "REG ADD \"HKCU\\Control Panel\\Desktop\" /V Wallpaper /T REG_SZ /F /D \"%s\" >NUL 2>&1" % image_path
      if os.system(command) != 0:
         log("Error running REG ADD")
      # stretch to fit
      command = "REG ADD \"HKCU\\Control Panel\\Desktop\" /V WallpaperStyle /T REG_SZ /F /D 2 >NUL 2>&1"
      if os.system(command) != 0:
         log("Error running REG ADD")
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

def applyCaption(options, wallpaper_image):
   # use ImageMagick to apply caption
   temp_file = os.path.join(options.temp_dir, os.path.basename(wallpaper_image) + ".caption.jpg")
   new_file  = os.path.join(options.temp_dir, os.path.basename(wallpaper_image) + ".composite.jpg")
   caption = os.path.splitext(os.path.basename(wallpaper_image))[0]
   log("Creating label: %s" % temp_file)
   command = "convert -size 300x28 -background \"#00000080\" -fill white label:\" %s \" \"miff:%s\"" % (caption, temp_file)
   os.system(command)
   log("Compositing: %s + %s => %s" % (temp_file, wallpaper_image, new_file))
   command = "composite -gravity south -geometry +0+50 \"%s\" \"%s\" \"%s\"" % (temp_file, wallpaper_image, new_file)
   os.system(command)
   log("Deleting: %s" % temp_file)
   os.unlink(temp_file)
   return new_file

def changeWallpaper(options, de, ev):
   if options.random:
      # get list of images
      dir_list = os.listdir(options.directory)
      # pick random one
      imagename = random.choice(dir_list)
   else:
      # select image based on time
      cur_time = time.localtime()
      imagename = "%02d" % cur_time.tm_hour + "." + options.extension
   wallpaper = options.directory + os.sep + imagename
   if os.path.exists(wallpaper):
      # check if we need to apply a caption
      if options.caption:
         wallpaper = applyCaption(options, wallpaper)
      de.setWallpaper(wallpaper)
   else:
      log("No wallpaper: " + wallpaper)
   # signal the event so the main thread knows this has completed
   log("change: setting")
   ev.set()

# command line input thread
class CommandLineThread(threading.Thread):
   def __init__(self, out_ev, fifo):
      self.out_ev = out_ev
      self.fifo = fifo
      threading.Thread.__init__(self)

   def run(self):
      command = ""
      while(command != "exit"):
         try:
            # python devs decided to rename raw_input() to input() in 3.x 
            # for no apparent reason.
            if sys.version_info < (3, 0):
               command = raw_input("queueWall> ")
            else:
               command = input("queueWall> ")
            if(command == "help"):
               print("Commands: exit, help, reload, restart")
            elif(command == "reload") or (command == "restart") or (command == "exit"):
               self.fifo.append(command)
               self.out_ev.set()
            else:
               print("Unknown command: %s" % command)
         except EOFError:
            command = "exit"
            self.fifo.append(command)
            self.out_ev.set()
      print("")
      log("CommandLine returning...")

#################################### main ######################################
if __name__ == "__main__":
   # command line arguments will override config file
   parser = optparse.OptionParser(usage="%prog [options]", version="%prog 0.00")
   parser.add_option("-c", "--command", help="custom command to change wallpaper [example: \"feh --bg-scale %s\"]",
                     default=queuewall_config.get("Configuration", "command"))
   parser.add_option("-C", "--caption", action="store_true",
                     help="Add caption with name of file before displaying",
                     default=queuewall_config.getboolean("Configuration", "caption"))
   parser.add_option("-d", "--directory",
                     help="wallpapers directory [default: %default]", 
                     default=queuewall_config.get("Directories", "wallpaper_dirs"))
   parser.add_option("-e", "--extension",
                     help="image extension [default: %default]",
                     default=queuewall_config.get("Directories", "image_extension"))
   parser.add_option("-i", "--interval",
                     help="interval between image rotations (in min) [default: %default]",
                     type="int",
                     default=queuewall_config.getint("Schedule", "interval"))
   parser.add_option("-l", "--log", action="store_true",
                     help="enable logging",
                     default=queuewall_config.getboolean("Configuration", "log"))
   parser.add_option("-r", "--random", action="store_true",
                     help="use random image from directory",
                     default=queuewall_config.getboolean("Configuration", "random"))
   parser.add_option("-s", "--system",
                     help="currently running system: autodetect, gnome, xfce4, lxde, windows [default: %default]",
                     default=queuewall_config.get("Configuration", "system"))
   parser.add_option("-t", "--terminal", action="store_true",
                     help="allow commands to be entered from terminal [default: %default]",
                     default=queuewall_config.getboolean("Configuration", "terminal"))
   parser.add_option("-T", "--temp_dir",
                     help="temporary directory to use for file conversions",
                     default=queuewall_config.get("Configuration", "temp_dir"))

   (options, args) = parser.parse_args()

   logInit(options.log)

   if options.temp_dir == DEFAULT_TEMP_DIR:
      options.temp_dir = tempfile.mkdtemp(prefix="queuewall")

   de = currentDE(options.system)
   if options.command != "":
      log("Using command: %s" % options.command)
      de.setCommand(options.command)

   # event flag to wait until thread completes
   de_ev = threading.Event()

   # call first time through to ensure background for current time is set
   changeWallpaper(options, de, de_ev)

   # spawn command line thread
   if options.terminal:
      fifo = []
      command_thread = CommandLineThread(de_ev, fifo).start()

   running = True
   try:
      while running:
         # clear event so it can be used again next time
         de_ev.clear()
         # sleep until the next hour rollover
         cur_time = time.localtime()
         # TODO: this is where the scheduler would figure out the delay
         if options.interval == 60:
            # if set to default 60, make it change on the hour
            delay_time = 60 * (60 - cur_time.tm_min) - cur_time.tm_sec
         else:
            # don't worry about the time, just delay the requested interval
            delay_time = 60 * options.interval
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
            elif(command == "reload"):
               log("main: reloading...")
               t.cancel()
               changeWallpaper(options, de, de_ev)
            elif(command != ""):
               log("main: command: %s" % command)
   except KeyboardInterrupt:
      print("Handling KeyboardInterrupt.  Exiting...")
      # Cancel the pending thread.  This can be called even if it has already started.
      t.cancel()

