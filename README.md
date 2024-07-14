# ASMARA-0.1.50
Automated System for Monitoring And Relaying Alerts (Older Version with Menu)

This is an older version of A-c0rN's [ASMARA](https://github.com/A-c0rN/ASMARA) project.

This version was decompiled from a binary that was sent out by Global Weather & EAS Society's EAS Relay Network (GWES ERN) network operations team sometime in 2021.

Special thanks to Jon, Marley and Aaron for helping me with this project and getting it to work.

This version has a menu that is a lot easier to use than the current version of the project and the code is a LOT less clunky and is significantly easier to understand than the new version.

This is version 0.1.50, the version A-c0rN has is 0.1.69, this version is when the software was referred to as "ERNDEC" and predates it being renamed to "ASMARA."

Here's instructions on how to use it the configuration if you're interested. I am not responsible for, and cannot possibly provide support for anything that you use this for. I am not liable to any damage to your computer from running this and I am not available for support for this project. Go bother A-c0rN if you want support for this, I'm simply uploading this for archival purposes.

----

Monitors: Add your monitors with quotations "http://{whatever}" (use comma if more than two monitors, but not on the last monitor)  
Callsign: Must be 8 letters  
Emulation: Can choose SAGE, TFT, whatnot  
Speaker: **do not change**  
Logger -   Self explanatory
  
Email does not work  
Enabled can be true, set your web hooks in the "webhooks thing"  
  
LocalFips: Put your local FIPS codes here. Used in the default RWT/DMO  

Playout: Only change icecast  
  
Waiting status is what it says when no song is playing  
Bitrate should not be changed (everything else there is self explanatory)  
  
Export: Audio logging  
  
Override: Play your own custom audio that interrupts music  
  
DJ:  
ID songs: Songs played before station ID or jingle  
  
  
Lead in: Plays EAS lead in audio  
Lead Out: same thing but after  
  
  
Filters:
  
Originators self explanatory  
Event codes self explanatory  
Same codes self explanatory  
Call signs: Must be 8 characters. Only allows alerts with the call sign to be ignored/relayed. Leave at "*" if you do not know what you are doing
  
  
Action:  
Ignore:Now (log only)  
Relay:Now (relays)  
Relay:Forced (idek)  
  
Notes:  
  
  
**ONLY MP3 AND WAV AUDIO FILES ARE SUPPORTED**  
**DO NOT FORGET COMMAS OR TO REMOVE COMMAS! **  
**USE RESPONSIBLY**
