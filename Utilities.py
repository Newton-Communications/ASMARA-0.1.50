"""
Note: Please do absolute imports, it allows me to clean up shit we don't use, and doesn't import extra code. It should be more efficient anyways.
"""
# Standard Library
from calendar import monthrange
from datetime import datetime as DT
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from io import BytesIO
from json import dump, loads
from os import system
from platform import system as osType
from random import randint
from smtplib import SMTP
from ssl import create_default_context
from threading import Lock, Thread
from time import localtime, timezone

# Third-Party
from discord_webhook import DiscordEmbed, DiscordWebhook
from EAS2Text.EAS2Text import EAS2Text
from plyer import notification


class severity(Enum):
    debug = "{}"  # For extra data text (Ex. Startup)
    info = "{}"  # For common text (Ex. Recv)
    warning = "WARNING > *** {} ***"  # For notice text (Ex. Monitor Down)
    error = "ERROR > *** {} ***"  # For critical error text (Ex. Program Error)


class Utilities:

    printLock = Lock()
    emailLock = Lock()

    defconfig = loads(
        """{
        "Monitors": [
            "http://127.0.0.1:8000/ACRN-SFT"
        ],
        "Callsign": "ACRN/SFT",
        "Emulation": "SAGE",
        "Speaker": false,
        "Logger": {
            "Notification": false,
            "Email": {
                "Enabled": false,
                "Server": "eas@server.com", 
                "Port": 587,
                "Username": "user",
                "Password": "hackme",
                "To": [
                    "user.name@server.com"
                ]
            },
            "Enabled": false,
            "Audio": false,
            "Webhooks": [
            ]
        },
        "LocalFIPS": [
            "00000"
        ],
        "PlayoutManager": {
            "Channels": 1,
            "SampleRate": 16000,
            "Icecast":{
                "Enabled": false,
                "WaitingStatus": "No Audio",
                "Address": "",
                "Port": "",
                "Source": "source",
                "Pass": "",
                "Mountpoint": "",
                "Bitrate": ""
            },
            "Audio": false,
            "Export": {
                "Enabled": false,
                "Folder": "OldAlerts"
            },
            "Override": {
                "Enabled": false,
                "Folder": "Override"
            },
            "AutoDJ": {
                "Enabled": false,
                "Folder": "PlayoutAudio",
                "IDFolder": "IDAudio",
                "IDSongs": 4
            },
            "LeadIn": {
                "Enabled": false,
                "File": "Leadin.wav",
                "Type": "wav"
            },
            "LeadOut": {
                "Enabled": false,
                "File": "Leadout.wav",
                "Type": "wav"
            },
        "Tone": false
        },
        "Filters":[
            {
                "Name": "Catch All",
                "Originators":[
                    "*"
                ],
                "EventCodes": [
                    "*"
                ],
                "SameCodes":[
                    "*"
                ],
                "CallSigns":[
                    "*"
                ],
                "Action": "Relay:Now"
            }
        ],
    "LogFile":".log"
    }"""
    )

    stats = loads(
        """{
        "EVENTS": {
            "ADR": "https://cdn.missingtextures.net/Icons/index.php?img=chat&hex=",
            "AVA": "https://cdn.missingtextures.net/Icons/index.php?img=avalanche&hex=",
            "AVW": "https://cdn.missingtextures.net/Icons/index.php?img=avalanche&hex=",
            "BHW": "https://cdn.missingtextures.net/Icons/index.php?img=biohazard&hex=",
            "BLU": "https://cdn.missingtextures.net/Icons/index.php?img=policeman&hex=",
            "BWW": "https://cdn.missingtextures.net/Icons/index.php?img=water-heating&hex=",
            "BZW": "https://cdn.missingtextures.net/Icons/index.php?img=snow&hex=",
            "CAE": "https://cdn.missingtextures.net/Icons/index.php?img=child-with-pacifier&hex=",
            "CDW": "https://cdn.missingtextures.net/Icons/index.php?img=break&hex=",
            "CEM": "https://cdn.missingtextures.net/Icons/index.php?img=break&hex=",
            "CFA": "https://cdn.missingtextures.net/Icons/index.php?img=beach&hex=",
            "CFW": "https://cdn.missingtextures.net/Icons/index.php?img=beach&hex=",
            "CHW": "https://cdn.missingtextures.net/Icons/index.php?img=biohazard&hex=",
            "CWW": "https://cdn.missingtextures.net/Icons/index.php?img=biohazard&hex=",
            "DBA": "https://cdn.missingtextures.net/Icons/index.php?img=dam&hex=",
            "DBW": "https://cdn.missingtextures.net/Icons/index.php?img=dam&hex=",
            "DEW": "https://cdn.missingtextures.net/Icons/index.php?img=biohazard&hex=",
            "DMO": "https://cdn.missingtextures.net/Icons/index.php?img=test-tube&hex=",
            "DSW": "https://cdn.missingtextures.net/Icons/index.php?img=wind&hex=",
            "EAN": "https://cdn.missingtextures.net/Icons/index.php?img=mushroom-cloud&hex=",
            "EAT": "https://cdn.missingtextures.net/Icons/index.php?img=mushroom-cloud&hex=",
            "EQW": "https://cdn.missingtextures.net/Icons/index.php?img=earthquakes&hex=",
            "EVA": "https://cdn.missingtextures.net/Icons/index.php?img=escape&hex=",
            "EVI": "https://cdn.missingtextures.net/Icons/index.php?img=escape&hex=",
            "EWW": "https://cdn.missingtextures.net/Icons/index.php?img=wind&hex=",
            "FCW": "https://cdn.missingtextures.net/Icons/index.php?img=biohazard&hex=",
            "FFS": "https://cdn.missingtextures.net/Icons/index.php?img=floods&hex=",
            "FFA": "https://cdn.missingtextures.net/Icons/index.php?img=floods&hex=",
            "FFW": "https://cdn.missingtextures.net/Icons/index.php?img=floods&hex=",
            "FLS": "https://cdn.missingtextures.net/Icons/index.php?img=sea-waves&hex=",
            "FLA": "https://cdn.missingtextures.net/Icons/index.php?img=sea-waves&hex=",
            "FLW": "https://cdn.missingtextures.net/Icons/index.php?img=sea-waves&hex=",
            "FRW": "https://cdn.missingtextures.net/Icons/index.php?img=fire&hex=",
            "FSW": "https://cdn.missingtextures.net/Icons/index.php?img=snowflake&hex=",
            "FZW": "https://cdn.missingtextures.net/Icons/index.php?img=snowflake&hex=",
            "HMW": "https://cdn.missingtextures.net/Icons/index.php?img=biohazard&hex=",
            "HUS": "https://cdn.missingtextures.net/Icons/index.php?img=hurricane&hex=",
            "HUA": "https://cdn.missingtextures.net/Icons/index.php?img=hurricane&hex=",
            "HUW": "https://cdn.missingtextures.net/Icons/index.php?img=hurricane&hex=",
            "HWA": "https://cdn.missingtextures.net/Icons/index.php?img=wind&hex=",
            "HWW": "https://cdn.missingtextures.net/Icons/index.php?img=wind&hex=",
            "IBW": "https://cdn.missingtextures.net/Icons/index.php?img=snowflake&hex=",
            "IFW": "https://cdn.missingtextures.net/Icons/index.php?img=fire&hex=",
            "LAE": "https://cdn.missingtextures.net/Icons/index.php?img=break&hex=",
            "LEW": "https://cdn.missingtextures.net/Icons/index.php?img=policeman&hex=",
            "LSW": "https://cdn.missingtextures.net/Icons/index.php?img=avalanche&hex=",
            "NAT": "https://cdn.missingtextures.net/Icons/index.php?img=speaker&hex=",
            "NIC": "https://cdn.missingtextures.net/Icons/index.php?img=chat&hex=",
            "NMN": "https://cdn.missingtextures.net/Icons/index.php?img=chat&hex=",
            "NPT": "https://cdn.missingtextures.net/Icons/index.php?img=test-tube&hex=",
            "NST": "https://cdn.missingtextures.net/Icons/index.php?img=quiet&hex=",
            "NUW": "https://cdn.missingtextures.net/Icons/index.php?img=radio-active&hex=",
            "POS": "https://cdn.missingtextures.net/Icons/index.php?img=electrical&hex=",
            "RHW": "https://cdn.missingtextures.net/Icons/index.php?img=radio-active&hex=",
            "RMT": "https://cdn.missingtextures.net/Icons/index.php?img=important-month&hex=",
            "RWT": "https://cdn.missingtextures.net/Icons/index.php?img=important-week&hex=",
            "SCS": "https://cdn.missingtextures.net/Icons/index.php?img=school&hex=",
            "SMW": "https://cdn.missingtextures.net/Icons/index.php?img=beach&hex=",
            "SPS": "https://cdn.missingtextures.net/Icons/index.php?img=rain&hex=",
            "SPW": "https://cdn.missingtextures.net/Icons/index.php?img=cottage&hex=",
            "SQW": "https://cdn.missingtextures.net/Icons/index.php?img=snow&hex=",
            "SSA": "https://cdn.missingtextures.net/Icons/index.php?img=beach&hex=",
            "SSW": "https://cdn.missingtextures.net/Icons/index.php?img=beach&hex=",
            "SVA": "https://cdn.missingtextures.net/Icons/index.php?img=cloudshot&hex=",
            "SVR": "https://cdn.missingtextures.net/Icons/index.php?img=cloudshot&hex=",
            "SVS": "https://cdn.missingtextures.net/Icons/index.php?img=rain&hex=",
            "TOA": "https://cdn.missingtextures.net/Icons/index.php?img=tornado&hex=",
            "TOR": "https://cdn.missingtextures.net/Icons/index.php?img=tornado&hex=",
            "TOE": "https://cdn.missingtextures.net/Icons/index.php?img=call&hex=",
            "TRA": "https://cdn.missingtextures.net/Icons/index.php?img=beach&hex=",
            "TRW": "https://cdn.missingtextures.net/Icons/index.php?img=beach&hex=",
            "TSA": "https://cdn.missingtextures.net/Icons/index.php?img=tsunami&hex=",
            "TSW": "https://cdn.missingtextures.net/Icons/index.php?img=tsunami&hex=",
            "TXB": "https://cdn.missingtextures.net/Icons/index.php?img=internet-antenna&hex=",
            "TXF": "https://cdn.missingtextures.net/Icons/index.php?img=internet-antenna&hex=",
            "TXO": "https://cdn.missingtextures.net/Icons/index.php?img=internet-antenna&hex=",
            "TXP": "https://cdn.missingtextures.net/Icons/index.php?img=internet-antenna&hex=",
            "VOA": "https://cdn.missingtextures.net/Icons/index.php?img=volcano&hex=",
            "VOW": "https://cdn.missingtextures.net/Icons/index.php?img=volcano&hex=",
            "WFA": "https://cdn.missingtextures.net/Icons/index.php?img=fire&hex=",
            "WFW": "https://cdn.missingtextures.net/Icons/index.php?img=fire&hex=",
            "WSA": "https://cdn.missingtextures.net/Icons/index.php?img=snow&hex=",
            "WSW": "https://cdn.missingtextures.net/Icons/index.php?img=snow&hex="
        }
    }
    """
    )

    # Class variable
    response = None
    unk = '797979'
    adv = 'FFCC00'
    wat = 'FF6600'
    war = 'FF0000'

    @classmethod
    def user_input(cls, timeout, cmdName="ENDEC", cmdText="Command"):
        cls.response = None

        def question():
            cls.autoPrint(
                text=f"{cmdText}: ",
                end="",
                classType=f"{cmdName}",
                severity=severity.info,
            )
            cls.response = input()

        t = Thread(target=question)
        t.daemon = True
        t.start()
        t.join(timeout)
        if cls.response:
            return cls.response
        else:
            return None

    @classmethod
    def genRandomWeekly(cls, TS: int = 0):
        oof = 0
        oof2 = 0
        randWeek = DT.utcnow().replace(second=0, microsecond=0)
        if TS != 0:
            if randWeek.timestamp() - TS < 604800:
                oof = 7 - randWeek.weekday()
                oof2 = randWeek.weekday()
        offset = (
            randWeek.day
            + (
                randint(randWeek.weekday() - oof2, 6)
                - (randWeek.weekday() - oof2)
            )
            + oof
        )
        try:
            randWeek = randWeek.replace(day=offset)
        except ValueError:
            upmonth = randWeek.month + 1 % 12
            if upmonth < randWeek.month:
                upyear = randWeek.year + 1
            else:
                upyear = randWeek.year
            test = offset % monthrange(upyear, upmonth)[1]
            randWeek = randWeek.replace(year=upyear, month=upmonth, day=test)
        randWeek = randWeek.replace(
            hour=randint(0, 23), minute=randint(0, 59)
        ).timestamp()
        return randWeek

    @classmethod
    def CLS(cls):
        if osType() == "Windows":
            system("cls")
        else:
            system("clear")

    @classmethod
    def getOS(cls):
        return osType()

    @classmethod
    def autoPrint(
        cls,
        text: str,
        classType: str = "ENDEC",
        severity: severity = severity.info,
        end: str = "\n",
    ):
        now = f"[{DT.now().strftime('%H:%M:%S')}{cls.getTZ()[0]}]"
        with cls.printLock:
            for line in text.split("\n"):
                print(
                    f"{now} > [{classType}] {severity.value.format(line)}",
                    end=end,
                )

    @classmethod
    def WriteDefConfig(cls):
        with open(".config", "w") as f:
            dump(cls.defconfig, f, indent=4)
        with open(".log", "w") as f:
            f.write('{"ACRN/SFT": {"Alerts":{}, "Weekly":{"Timestamp": 0}}}')

    @classmethod
    def isInt(cls, number):
        try:
            int(number)
        except ValueError:
            return False
        else:
            return True

    @classmethod
    def getTZ(cls):
        tzone = str(timezone / 3600.0)
        locTime = localtime().tm_isdst
        TMZ = "UTC"
        if tzone == "4.0":
            TMZ = "AST"
            if locTime > 0 == True:
                TMZ = "ADT"
        elif tzone == "5.0":
            TMZ = "EST"
            if locTime > 0 == True:
                TMZ = "EDT"
        elif tzone == "6.0":
            TMZ = "CST"
            if locTime > 0 == True:
                TMZ = "CDT"
        elif tzone == "7.0":
            TMZ = "MST"
            if locTime > 0 == True:
                TMZ = "MDT"
        elif tzone == "8.0":
            TMZ = "PST"
            if locTime > 0 == True:
                TMZ = "PDT"
        return TMZ

    @classmethod
    def genEmailSig(cls, call, version):
        return f"""<div class="moz-signature"><div class="WordSection1"><table class="MsoNormalTable" style="border-collapse: collapse;" border="0" width="499" cellspacing="0" cellpadding="0"><tbody><tr style="mso-yfti-irow: 0; mso-yfti-firstrow: yes;"><td style="width: 5.5in; padding: 0in 0in 0in 0in;" width="528">&nbsp;</td></tr><tr style="mso-yfti-irow: 2; height: 88.15pt;"><td style="width: 5.5in; border: none; border-bottom: dotted windowtext 1.0pt; padding: 0in 0in 0in 0in; height: 88.15pt;" width="528"><table class="MsoNormalTable" style="border-collapse: collapse; height: 5px;" border="0" width="524" cellspacing="0" cellpadding="0"><tbody><tr style="mso-yfti-irow: 0; mso-yfti-firstrow: yes; mso-yfti-lastrow: yes;"><td style="width: 75.25pt; padding: 2.9pt 0in 2.9pt 0in;" width="100"><p class="MsoNormal"><span style="font-family: Poppins; mso-fareast-font-family: 'Times New Roman'; mso-no-proof: yes;"><img src="https://f2.toyhou.se/file/f2-toyhou-se/images/61847631_ID0K8200RoAF6ee.png" style="width: 137px; height: auto"/><br /></span></p></td><td style="width: 390.25pt; padding: 2.9pt 0in 2.9pt 0in;" width="520"><span style="font-size: 9.0pt; font-family: Poppins; mso-fareast-font-family: 'Times New Roman'; mso-no-proof: yes;"></span><table class="MsoNormalTable" style="border-collapse: collapse;" border="0" width="358" cellspacing="0" cellpadding="0"><tbody><tr style="mso-yfti-irow: 0; mso-yfti-firstrow: yes;"><td style="width: 257.5pt; padding: 2.9pt 5.75pt 2.9pt 5.75pt;" width="343"><p class="MsoNormal"><span style="font-family: Verdana;"><strong>{call} Software ENDEC Logs</strong></span><br /><span style="font-family: Poppins; mso-fareast-font-family: 'Times New Roman'; mso-no-proof: yes;"> </span></p><p class="MsoNormal"><span style="font-size: 9.0pt; font-family: Poppins; mso-fareast-font-family: 'Times New Roman'; mso-no-proof: yes;"><span style="font-family: Verdana;">Do Not Reply, This is a Software-Generated Message.</span></span><br /><span style="font-family: Verdana;"><span style="font-size: 9pt;"></span></span></p><span style="font-size: 9.0pt; font-family: Poppins; mso-fareast-font-family: 'Times New Roman'; mso-no-proof: yes;"><span style="font-family: Verdana;"> </span></span></td></tr><tr style="mso-yfti-irow: 1;"><td style="width: 257.5pt; padding: 2.9pt 5.75pt 2.9pt 5.75pt;" width="343"><p class="MsoNormal"><span style="font-family: Verdana;"><span style="font-size: 8.0pt; font-family: 'Poppins Light'; mso-fareast-font-family: 'Times New Roman'; color: #7f7f7f; mso-no-proof: yes;">ASMARA EAS-DEC Version {version}</span></span><span style="font-size: 8.0pt; font-family: 'Poppins Light'; mso-fareast-font-family: 'Times New Roman'; mso-no-proof: yes;"></span></p><p class="MsoNormal"><span style="font-size: 8.0pt; font-family: 'Poppins Light'; mso-fareast-font-family: 'Times New Roman'; color: #7f7f7f; mso-no-proof: yes;"><span style="font-family: Verdana;">© 2022<span style="mso-spacerun: yes;"> </span> <a href="https://example.com">ASMARA</a></span></span></p></td></tr></tbody></table></td></tr></tbody></table></td></tr><tr style="mso-yfti-irow: 3; mso-yfti-lastrow: yes; height: 3.0pt;"><td style="width: 5.5in; padding: 0in 0in 0in 0in; height: 3.0pt;" width="528"><p class="MsoNormal" style="text-align: center;"><strong><span style="font-size: 7.0pt; font-family: Poppins; mso-fareast-font-family: 'Times NewRoman'; color: #70ad47; mso-no-proof: yes;"><span style="color: #18ff00; font-family: Verdana;">P</span></span></strong><span style="color: #18ff00; font-family: Verdana;"><span style="font-size: 7pt;">&nbsp;Save a tree. Don't print this e-mail unless it's necessary.</span></span><span style="font-family: Poppins; mso-fareast-font-family: 'Times New Roman'; mso-no-proof: yes;"> </span></p></td></tr></tbody></table><p class="MsoNormal">&nbsp;</p></div></div>"""

    @classmethod
    def sendEmail(
        cls,
        station: str,
        alertTitle: str,
        relay: str,
        mon: str,
        filt: str,
        EASData: EAS2Text,
        header: str,
        version: str,
        mon2: str,
        filt2: str,
        server: tuple,
    ):
        try:
            message = MIMEMultipart("alternative")
            message[
                "Subject"
            ] = f"{station.strip()} Software ENDEC: - {alertTitle}"
            message[
                "From"
            ] = f"{station.strip()} Software ENDEC Logs <{server['Username']}>"
            message["To"] = ", ".join(server["To"])
            html = f"""
                    <h3><strong>{alertTitle} - {relay}</strong></h3>
                    <p>{mon if mon != "" else ""}{filt if filt != "" else ""}
                    <b>EAS Text Translation:</b> {EASData.EASText}
                    <br><br>
                    <b>EAS Protocol Data:</b> {header}
                    </p>
                    {cls.genEmailSig(station, version)}
                """
            text = f"----AUTOMATED MESSAGE---\n\n{alertTitle} - {relay}\n{mon2}{filt2}\nEAS Text Translation:\n{EASData.EASText}\n\nEAS Protocol Data:\n{header}\n\n------DO NOT REPLY------\n(SENT FROM ERN-DEC VERSION {version})"
            part1 = MIMEText(text, "plain")
            part2 = MIMEText(html, "html")
            message.attach(part1)
            message.attach(part2)
            context = create_default_context()
            with SMTP(server["Server"], server["Port"]) as mailServ:
                # server.starttls(context=context) ##DISABLED TLS UNTIL PYTHON GETS THIER SHIT TOGETHER
                mailServ.login(server["Username"], server["Password"])
                mailServ.sendmail(
                    server["Username"], server["To"], message.as_string()
                )
            cls.autoPrint(
                text="Successfully Sent Email!",
                classType="EMAIL",
                severity=severity.info,
            )
        except Exception as E:
            cls.autoPrint(
                text=f"{type(E).__name__}, {E}",
                classType="EMAIL",
                severity=severity.error,
            )
            tb = E.__traceback__
            while tb is not None:
                cls.autoPrint(
                    text=f"File: {tb.tb_frame.f_code.co_filename}\nFunc: {tb.tb_frame.f_code.co_name}\nLine: {tb.tb_lineno}",
                    classType="EMAIL",
                    severity=severity.error,
                )
                tb = tb.tb_next
            cls.autoPrint(
                text="Failed to send Email to Server. Please check Email configurations.",
                classType="EMAIL",
                severity=severity.error,
            )

    @classmethod
    def sendNotification(cls, station, notif, alert: bool = True):
        try:
            notification.notify(
                title=f"{station.strip()} {'Alert ' if alert else 'Update '}Log:",
                message=notif,
                app_icon="./test.ico",
                timeout=5,
            )
            cls.autoPrint(
                text="Successfully Sent Notification!",
                classType="NOTIFICATION",
                severity=severity.info,
            )
        except Exception as E:
            cls.autoPrint(
                text=f"{type(E).__name__}, {E}",
                classType="NOTIFICATION",
                severity=severity.error,
            )
            tb = E.__traceback__
            while tb is not None:
                cls.autoPrint(
                    text=f"File: {tb.tb_frame.f_code.co_filename}\nFunc: {tb.tb_frame.f_code.co_name}\nLine: {tb.tb_lineno}",
                    classType="NOTIFICATION",
                    severity=severity.error,
                )
                tb = tb.tb_next
            cls.autoPrint(
                text="Failed to send Desktop Notification. If running headless, please disable Notifications.",
                classType="NOTIFICATION",
                severity=severity.error,
            )

    @classmethod
    def log(
        cls,
        station: str,
        webhooks: list,
        status: str,
        header: str,
        filter: str = "",
        monitorNum: str = "",
        AudioLog: bool = False,
        AudioFile="",  ## Will take a String or a List object.
        server: str = "",
        version: str = "0.0.0",
        oldEmbed=None,
        notification: bool = False,
        email=False,
    ):
        """Logs the incoming data to Discord, Email, or Desktop

        Args:
            station (str): The callsign of the current station.
            webhooks (list): The discord webhooks to send the logs to.
            status (str): The status message to associate the alert to, such as "Recieved Alert Sent".
            header (str): The SAME data.
            filter (str, optional): A ENDEC filter to say matched against. Defaults to "".
            monitorNum (str, optional): The monitor number the alert was received on. Defaults to "".
            AudioLog (bool, optional): Is there an audio file? Defaults to False.
            AudioFile (str or list, optional): Path to audio if str, OR a list in the format of [Filename, BytesIO Object]. Defaults to "".
            version (str, optional): ENDEC version string. Defaults to "0.0.0".
            oldEmbed (_type_, optional): A previous EMBED to update. Defaults to None.
            notification (bool, optional): Send Desktop Notification? Defaults to False.
            email (bool, optional): Send Email? Defaults to False.

        Returns:
            _type_: _description_
        """

        EASData = EAS2Text(header)
        try:
            alertTitle = " ".join(EASData.evntText.split(" ")[1:])
            if any(
                word.lower() in alertTitle.lower()
                for word in [
                    "Demo",
                    "Test",
                    "Advisory",
                    "Statement",
                    "Administrative",
                    "Practice",
                    "Transmitter",
                    "Network",
                ]
            ):
                color = cls.adv
            elif any(word.lower() in alertTitle.lower() for word in ["Watch"]):
                color = cls.wat
            elif any(
                word.lower() in alertTitle.lower()
                for word in [
                    "Warning",
                    "Emergency",
                    "Alert",
                    "Evacuation",
                    "Notification",
                    "Action",
                    "Center",
                ]
            ):
                color = cls.war
            else:
                color = cls.unk
            alertImage = str(cls.stats["EVENTS"][EASData.evnt]) + str(
                color
            )
        except Exception as e:
            # print(e)
            alertTitle = f"Unknown Alert ({header.split('-')[2]})"
            color = cls.unk
            alertImage = (
                "http://caseymediallc.com/Icons/index.php?img=break&hex="
                + str(color)
            )
        relay = f"{status} at {DT.now().strftime('%m/%d/%Y %H:%M:%S ') + cls.getTZ()}"
        if server == "Audio":
            server = "Local Audio Monitor"
        elif server == "Radio":
            server = "Local SDR Monitor"
        notif = ""
        mon = ""
        mon2 = ""
        filt = ""
        filt2 = ""
        embed = DiscordEmbed(title=alertTitle, description=relay, color=color)
        embed.set_author(name=f"{station.strip()} - Software ENDEC Logs")
        embed.set_footer(text=f"EAS-DEC {version} | © 2022 ASMARA Tech.")
        if monitorNum != "" and server != "":
            embed.add_embed_field(
                name="Recieved From:",
                value=f"Monitor #{monitorNum}\n({server})",
                inline=True,
            )
            notif += f"Recieved From: {monitorNum}\n"
            mon = f"<b>Received From:</b> {monitorNum} <small>({server})</small><br>"
            mon2 = f"\nRecieved From: {monitorNum} ({server})\n"
        if filter != "":
            embed.add_embed_field(
                name="Matched Filter:", value=filter, inline=True
            )
            notif += f"Matched Filter: {filter}\n"
            filt = f"<b>Matched Filter:</b> {filter}<br><br>"
            filt2 = f"Matched Filter: {filter}\n"
        embed.add_embed_field(
            name="EAS Text Data:",
            value=f"```{EASData.EASText}```",
            inline=False,
        )
        notif += f"{EASData.EASText}\n"
        embed.add_embed_field(
            name="EAS Protocol Data:", value=f"```{header}```", inline=False
        )
        if alertImage:
            embed.set_thumbnail(url=alertImage)
        webhook = DiscordWebhook(url=webhooks, rate_limit_retry=True)
        webhook.add_embed(embed)
        try:
            if oldEmbed:
                if AudioLog == True:
                    if type(AudioFile) == str:
                        with open(AudioFile, "rb") as f:
                            webhook.add_file(file=f.read(), filename=AudioFile)
                            f.close()
                    elif type(AudioFile) == list:
                        webhook.add_file(
                            file=AudioFile[1], filename=AudioFile[0]
                        )
                        f.close()
                oldLog = webhook.edit(oldEmbed)
                cls.autoPrint(
                    text="Successfully Updated Webhook!",
                    classType="LOGGER",
                    severity=severity.info,
                )
                if notification:
                    cls.sendNotification(station, notif)
            else:
                if AudioLog == True:
                    if type(AudioFile) == str:
                        with open(AudioFile, "rb") as f:
                            webhook.add_file(file=f.read(), filename=AudioFile)
                            f.close()
                    elif type(AudioFile) == list:
                        webhook.add_file(
                            file=AudioFile[1], filename=AudioFile[0]
                        )
                        f.close()
                oldLog = webhook.execute()
                cls.autoPrint(
                    text="Successfully Posted Log to Webhook!",
                    classType="LOGGER",
                    severity=severity.info,
                )
                if notification:
                    cls.sendNotification(station, notif)
                if email:
                    with cls.emailLock:
                        cls.sendEmail(
                            station,
                            alertTitle,
                            relay,
                            mon,
                            filt,
                            EASData,
                            header,
                            version,
                            mon2,
                            filt2,
                            email,
                        )
        except Exception as E:
            cls.autoPrint(
                text=f"{type(E).__name__}, {E}",
                classType="LOGGER",
                severity=severity.error,
            )
            tb = E.__traceback__
            while tb is not None:
                cls.autoPrint(
                    text=f"File: {tb.tb_frame.f_code.co_filename}\nFunc: {tb.tb_frame.f_code.co_name}\nLine: {tb.tb_lineno}",
                    classType="LOGGER",
                    severity=severity.error,
                )
                tb = tb.tb_next
            cls.autoPrint(
                text="Failed to send Log to Discord, Check your connection, or webhooks.",
                classType="LOGGER",
                severity=severity.error,
            )
        return oldLog

    @classmethod
    def ioObject(cls, data: bytes) -> BytesIO:
        """Generates a BytesIO File-like object with the included data

        Args:
            data (bytes): The data to input to the BytesIO Object

        Returns:
            BytesIO: The File-like BytesIO Object
        """
        object = BytesIO(data)

        return object
