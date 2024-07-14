"""
Note: Please do absolute imports, it allows me to clean up shit we don't use, and doesn't import extra code. It should be more efficient anyways.
"""
# Standard Library
from datetime import datetime as DT
from json import dump, load
from multiprocessing import Process
from os import getcwd, path, remove, walk
from random import choice, shuffle
from subprocess import PIPE, Popen
from sys import argv, exit
from threading import Thread
from time import mktime, sleep
from warnings import filterwarnings

# Third-Party
from EAS2Text.EAS2Text import EAS2Text
from EASGen.EASGen import EASGen
from numpy import append, blackman, empty, fft, float32, frombuffer, int16, log, log10
from pyaudio import PyAudio, paInt16
from pydub import AudioSegment
from pydub.effects import normalize
from pydub.generators import Sine
from pydub.utils import make_chunks, mediainfo
from requests import get

# First-Party
from Utilities import Utilities, severity

filterwarnings("ignore")

CurrentAlert = []

## TODO: Write a new message handler here to replace `print` statements, This will allow us to control the levels of logging like the Logging module without using the logging module (It's annoying.) Maybe even write it into a new file or the Utilities program?


class EndecMon(Process):

    global CurrentAlert
    monitors = {}
    receivedAlerts = {}
    receivedAlertsIndex = []
    pendingAlerts = {}
    run = True

    def __init__(self, URL: str = "") -> None:
        self.monitorName = None
        self.monitor = {
            "Type": "Stream",
            "URL": URL,
            "State": True,
            "Online": True,
            "Alert": False,
            "AttentionTone": False,
        }
        if isinstance(URL, dict):
            if "AUD" in URL:
                self.monitor["Type"] = "Audio"
                self.monitor["URL"] = URL["AUD"]
            elif "SDR" in URL:
                Utilities.autoPrint(
                    text="SDR Monitor unsupported!",
                    classType="ENDEC",
                    severity=severity.info,
                )
                self.monitor["Type"] = "Radio"
                self.monitor["URL"] = URL["AUD"]
                self.monitor["State"] = False
                self.monitor["Online"] = False
                self.updateMon(self.monitorName, self.monitor)
                return
        num = 1
        while self.monitorName == None:
            if str(num) in self.monitors:
                num = num + 1
            else:
                self.monitorName = str(num)
                self.updateMon(self.monitorName, self.monitor)
        self.decode = None
        self.stream = None
        self.AlertData = {}
        self.decThread = Thread(
            target=self.decoder,
            name=f"Decoder-{self.monitorName}",
            daemon=True,
        )
        self.monThread = Thread(
            target=self.recorder,
            name=f"Recorder-{self.monitorName}",
            daemon=True,
        )
        self.monThread.start()
        self.decThread.start()
        Utilities.autoPrint(
            text=f"Monitor {self.monitorName}: Created.",
            classType="ENDEC",
            severity=severity.info,
        )

    def killMon(self):
        self.monitor["State"] = False
        self.decode.terminate()
        self.decode.poll()
        self.stream.terminate()
        self.stream.poll()
        try:
            del self.monitors[self.monitorName]
        except ValueError:
            pass
        return

    @classmethod
    def updateMon(cls, monName, mon):
        cls.monitors[monName] = mon

    def MonState(self, update: bool = False):
        if update:
            self.updateMon(self.monitorName, self.monitor)
        else:
            return (
                "Online"
                if self.monitor["Online"]
                else "Offline"
                if self.monitor["State"]
                else "Disabled"
            )

    def ATTNDetection(self, pkt, bufferSize, sampleRate, window):
        dBDect = 10
        fin = []
        bandPasses = [
            (
                float((800 / (sampleRate / bufferSize)) + 1),
                float((900 / (sampleRate / bufferSize)) - 1),
                [851, 852, 853, 854, 855],
            ),
            (
                float((900 / (sampleRate / bufferSize)) + 1),
                float((1000 / (sampleRate / bufferSize)) - 1),
                [958, 959, 960, 961, 962],
            ),
            (
                float((1000 / (sampleRate / bufferSize)) + 1),
                float((2000 / (sampleRate / bufferSize)) - 1),
                [1048, 1049, 1050, 1051, 1052],
            ),
        ]
        try:
            for bandPass in bandPasses:
                if len(pkt) == bufferSize:
                    indata = pkt * window
                    bp = fft.rfft(indata)
                    minFilterBin = bandPass[0]
                    maxFilterBin = bandPass[1]
                    for i in range(len(bp)):
                        if i < minFilterBin:
                            bp[i] = 0
                        if i > maxFilterBin:
                            bp[i] = 0
                    fftData = abs(bp) ** 2
                    which = fftData[1:].argmax() + 1
                    dB = 10 * log10(1e-20 + abs(bp[which]))
                    if round(dB) >= dBDect:
                        if which != len(fftData) - 1:
                            y0, y1, y2 = log(fftData[which - 1 : which + 2 :])
                            x1 = (y2 - y0) * 0.5 / (2 * y1 - y2 - y0)
                            thefreq = (which + x1) * sampleRate / bufferSize
                        else:
                            thefreq = which * sampleRate / bufferSize
                        if round(thefreq) in bandPass[2]:
                            fin.append(True)
                        else:
                            fin.append(False)
                    else:
                        fin.append(False)
                else:
                    fin.append(False)
            if (fin[0] and fin[1]) or fin[2] or (fin[0] and fin[1] and fin[2]):
                return True
            else:
                return False
        except:
            return False

    # NEED EAN MANAGER THINGY

    @classmethod
    def AlertToOld(cls, ZCZC, Alert):
        if ZCZC in cls.receivedAlertsIndex:
            cls.receivedAlerts[ZCZC] = Alert
        else:
            cls.receivedAlerts[ZCZC] = Alert
            cls.receivedAlertsIndex.append(ZCZC)

    @classmethod
    def AlertFromOld(cls, Index: int = 0) -> dict:
        try:
            alert = cls.receivedAlertsIndex.pop(Index)
            prevAlert = cls.receivedAlerts.pop(alert)
        except Exception as E:
            Utilities.autoPrint(
                text=f"{type(E).__name__}, {E}",
                classType="ENDEC",
                severity=severity.error,
            )
            tb = E.__traceback__
            while tb is not None:
                Utilities.autoPrint(
                    text=f"File: {tb.tb_frame.f_code.co_filename}\nFunc: {tb.tb_frame.f_code.co_name}\nLine: {tb.tb_lineno}",
                    classType="ENDEC",
                    severity=severity.error,
                )
                tb = tb.tb_next
        return {alert: prevAlert}

    def decoder(self):
        try:
            os = Utilities.getOS()
            if os == "Darwin":
                self.decode = Popen(
                    ["./samedecMac", "-r", "24000"],
                    stdout=PIPE,
                    stdin=PIPE,
                    stderr=PIPE,
                    bufsize=1,
                )
            elif os == "Windows":
                self.decode = Popen(
                    ["./samedecWindows.exe", "-r", "24000"],
                    stdout=PIPE,
                    stdin=PIPE,
                    stderr=PIPE,
                    bufsize=1,
                )
            elif os == "Linux":
                self.decode = Popen(
                    ["./samedecLinux", "-r", "24000"],
                    stdout=PIPE,
                    stdin=PIPE,
                    stderr=PIPE,
                    bufsize=1,
                )
            else:
                self.decode = Popen(
                    ["./samedec", "-r", "24000"],
                    stdout=PIPE,
                    stdin=PIPE,
                    stderr=PIPE,
                    bufsize=1,
                )
        except FileNotFoundError:
            Utilities.autoPrint(
                    text=f"Compiled SAMEDEC Version is not 0.2.1 and/or invalid, using Built-In...",
                    classType="DECODER",
                    severity=severity.warning,
                )
        # try:
        #     if (
        #         Popen(["./samedec", "-V"], stdout=PIPE)
        #         .communicate()[0]
        #         .decode("UTF-8")
        #         .strip()
        #         == "samedec 0.2.1"
        #     ):
        #         self.decode = Popen(
        #             ["./samedec", "-r", "24000"],
        #             stdout=PIPE,
        #             stdin=PIPE,
        #             stderr=PIPE,
        #             bufsize=1,
        #         )
        #     else:
        #         Utilities.autoPrint(
        #             text=f"Compiled SAMEDEC Version is not 0.2.1, using Built-In...",
        #             classType="DECODER",
        #             severity=severity.warning,
        #         )
        #         raise FileNotFoundError
        # except FileNotFoundError:
        #     os = Utilities.getOS()
        #     if os == "Darwin":
        #         self.decode = Popen(
        #             ["./samedecMac", "-r", "24000"],
        #             stdout=PIPE,
        #             stdin=PIPE,
        #             stderr=PIPE,
        #             bufsize=1,
        #         )
        #     elif os == "Windows":
        #         self.decode = Popen(
        #             ["./samedecWindows", "-r", "24000"],
        #             stdout=PIPE,
        #             stdin=PIPE,
        #             stderr=PIPE,
        #             bufsize=1,
        #         )
        #     else:
        #         self.decode = Popen(
        #             ["./samedec", "-r", "24000"],
        #             stdout=PIPE,
        #             stdin=PIPE,
        #             stderr=PIPE,
        #             bufsize=1,
        #         )
        while self.run:
            if not self.monitor["State"]:
                sleep(1)
            else:
                try:
                    decode = (
                        self.decode.stdout.readline()
                        .decode("utf-8")
                        .strip("\n")
                    )
                    if "ZCZC" in decode:
                        noCall = "-".join(decode.split("-")[:-2]) + "-"
                        EASData = EAS2Text(decode)
                        Utilities.autoPrint(
                            text=f"Monitor {self.monitorName}: Receiving Alert:\n{EASData.EASText}\n{decode}",
                            classType="DECODER",
                            severity=severity.info,
                        )
                        try:
                            if noCall in self.receivedAlerts:
                                Utilities.autoPrint(
                                    text=f"Monitor {self.monitorName}: Alert already processed.",
                                    classType="DECODER",
                                    severity=severity.info,
                                )
                                self.monitor["Alert"] = False
                            else:
                                x = DT.strptime(
                                    decode.split("-")[-3], "%j%H%M"
                                )
                                timestamp = decode.split("-")[-4].split("+")[1]
                                EndTime = mktime(
                                    DT(
                                        DT.utcnow().year,
                                        x.month,
                                        x.day,
                                        x.hour,
                                        x.minute,
                                    ).timetuple()
                                ) + (
                                    (int(timestamp[:2]) * 60) * 60
                                    + int(timestamp[2:]) * 60
                                )
                                now = mktime(DT.utcnow().timetuple())
                                ## Utilities.autoPrint(now, EndTime)
                                if now >= EndTime:
                                    Utilities.autoPrint(
                                        text=f"Monitor {self.monitorName}: Alert is Expired.",
                                        classType="DECODER",
                                        severity=severity.info,
                                    )
                                    self.monitor["Alert"] = False
                                else:
                                    filt = self.FilterManager(
                                        EASData.org,
                                        EASData.evnt,
                                        EASData.FIPS,
                                        EASData.callsign,
                                    )
                                    if filt["Matched"]:
                                        self.AlertData = {
                                            "Monitor": f"Monitor {self.monitorName}",
                                            "Time": now,
                                            "Event": " ".join(
                                                EASData.evntText.split(" ")[1:]
                                            ),
                                            "Protocol": noCall,
                                            "From": EASData.callsign,
                                            "Filter": filt,
                                            "Length": 0,
                                        }
                                        if not "Ignore" in filt["Actions"]:
                                            self.AlertToOld(
                                                noCall, self.AlertData
                                            )
                                            if EndecManager.logger:
                                                self.log = Utilities.log(
                                                    EndecManager.callsign,
                                                    EndecManager.webhooks,
                                                    "Recieving alert",
                                                    decode,
                                                    filt["Name"],
                                                    self.monitorName,
                                                    False,
                                                    "",
                                                    self.monitor["URL"],
                                                    EndecManager.version,
                                                    notification=EndecManager.notification,
                                                    email=EndecManager.email,
                                                )
                                            self.monitor["Alert"] = True
                                        else:
                                            if not "Now" in filt["Actions"]:
                                                self.AlertToOld(
                                                    noCall, self.AlertData
                                                )
                                                if EndecManager.logger:
                                                    self.log = Utilities.log(
                                                        EndecManager.callsign,
                                                        EndecManager.webhooks,
                                                        "Recieving alert",
                                                        decode,
                                                        filt["Name"],
                                                        self.monitorName,
                                                        False,
                                                        "",
                                                        self.monitor["URL"],
                                                        EndecManager.version,
                                                        notification=EndecManager.notification,
                                                        email=EndecManager.email,
                                                    )
                                                self.monitor["Alert"] = True
                                            else:
                                                self.monitor["Alert"] = False
                                                Utilities.autoPrint(
                                                    text=f"Monitor {self.monitorName}: Alert Filter is Ignore.",
                                                    classType="DECODER",
                                                    severity=severity.info,
                                                )
                                                self.AlertToOld(
                                                    noCall, self.AlertData
                                                )
                                                if EndecManager.logger:
                                                    Utilities.log(
                                                        EndecManager.callsign,
                                                        EndecManager.webhooks,
                                                        "Alert Ignored",
                                                        decode,
                                                        filt["Name"],
                                                        self.monitorName,
                                                        False,
                                                        "",
                                                        self.monitor["URL"],
                                                        EndecManager.version,
                                                        notification=EndecManager.notification,
                                                        email=EndecManager.email,
                                                    )
                                    else:
                                        Utilities.autoPrint(
                                            text=f"Monitor {self.monitorName}: Alert is Not in Filter.",
                                            classType="DECODER",
                                            severity=severity.info,
                                        )
                                        self.monitor["Alert"] = False
                        except ValueError:
                            Utilities.autoPrint(
                                text=f"Monitor {self.monitorName}: EAS Data is INVALID: {decode}",
                                classType="DECODER",
                                severity=severity.info,
                            )
                            self.monitor["Alert"] = False
                    elif "NNNN" and self.monitor["Alert"]:
                        Utilities.autoPrint(
                            text=f"Monitor {self.monitorName}: EOMs Recieved.",
                            classType="DECODER",
                            severity=severity.info,
                        )
                        self.monitor["Alert"] = False
                except Exception as E:
                    if self.run:
                        Utilities.autoPrint(
                            text=f"Monitor {self.monitorName}: {type(E).__name__}, {E}",
                            classType="DECODER",
                            severity=severity.error,
                        )
                        tb = E.__traceback__
                        while tb is not None:
                            Utilities.autoPrint(
                                text=f"File: {tb.tb_frame.f_code.co_filename}\nFunc: {tb.tb_frame.f_code.co_name}\nLine: {tb.tb_lineno}",
                                classType="DECODER",
                                severity=severity.error,
                            )
                            tb = tb.tb_next
        Utilities.autoPrint(
            text=f"Monitor {self.monitorName}: Closing Decoder Thread.",
            classType="DECODER",
            severity=severity.info,
        )
        return

    def FilterManager(self, ORG, EVNT, FIPS, CALL):
        Utilities.autoPrint(
            text=f"Monitor {self.monitorName}: Checking Filters...",
            classType="FILTER",
            severity=severity.info,
        )
        try:
            filters = EndecManager.filters
            for filter in filters:
                OOO, EEE, SSS, CCC = False, False, False, False
                Name, Orgs, Evnts, Sames, Calls, Actions = (
                    filter["Name"],
                    filter["Originators"],
                    filter["EventCodes"],
                    filter["SameCodes"],
                    filter["CallSigns"],
                    filter["Action"],
                )
                if "LOCAL" in Sames or "LOC" in Sames:
                    Sames.append(EndecManager.localFIPS)
                if ("*" in Orgs) or (ORG in Orgs):
                    OOO = True
                else:
                    OOO = False
                if ("*" in Evnts) or (EVNT in Evnts):
                    EEE = True
                else:
                    EEE = False
                if ("*" in Calls) or (CALL.strip() in Calls):
                    CCC = True
                else:
                    CCC = False
                for Same in Sames:
                    if Same == "*":
                        SSS = True
                        break
                    elif (len(Same) == 6 and Same.startswith("*") and Same.endswith("***")):
                        for FIP in FIPS:
                            if FIP[1:3] == Same[1:3]:
                                SSS = True
                                break
                    elif len(Same) == 6 and Same.startswith("*"):
                        for FIP in FIPS:
                            if FIP[-5:] == Same[-5:]:
                                SSS = True
                                break
                    elif len(Same) == 6 and Same.endswith("***"):
                        for FIP in FIPS:
                            if FIP[:3] == Same[:3]:
                                SSS = True
                                break
                    elif len(Same) == 6:
                        for FIP in FIPS:
                            if FIP == Same:
                                SSS = True
                                break
                    else:
                        SSS = False
                        break
                if OOO and EEE and SSS and CCC:
                    return {"Matched": True, "Name": Name, "Actions": Actions}
            return {"Matched": False}
        except Exception as E:
            Utilities.autoPrint(
                text=f"Monitor {self.monitorName}: {type(E).__name__}, {E}",
                classType="FILTER",
                severity=severity.error,
            )
            tb = E.__traceback__
            while tb is not None:
                Utilities.autoPrint(
                    text=f"File: {tb.tb_frame.f_code.co_filename}\nFunc: {tb.tb_frame.f_code.co_name}\nLine: {tb.tb_lineno}",
                    classType="FILTER",
                    severity=severity.error,
                )
                tb = tb.tb_next

    def recorder(self):
        if self.monitor["Type"] == "Audio":
            try:
                os = Utilities.getOS()
                if os == "Darwin":
                    cmd = [
                        "ffmpeg",
                        "-hide_banner",
                        "-nostdin",
                        "-loglevel",
                        "warning",
                        "-i",
                        self.monitor["URL"],
                        "-f",
                        "f32le",
                        "-acodec",
                        "pcm_f32le",
                        "-ar",
                        "24000",
                        "-ac",
                        "1",
                        "-",
                    ]
                elif os == "Windows":
                    cmd = [
                        "ffmpeg",
                        "-hide_banner",
                        "-nostdin",
                        "-loglevel",
                        "warning",
                        "-f",
                        "pulse",
                        "-i",
                        self.monitor["URL"],
                        "-f",
                        "f32le",
                        "-acodec",
                        "pcm_f32le",
                        "-ar",
                        "24000",
                        "-ac",
                        "1",
                        "-",
                    ]
                elif os == "Linux":
                    cmd = [
                        "ffmpeg",
                        "-hide_banner",
                        "-nostdin",
                        "-loglevel",
                        "warning",
                        "-i",
                        self.monitor["URL"],
                        "-f",
                        "f32le",
                        "-acodec",
                        "pcm_f32le",
                        "-ar",
                        "24000",
                        "-ac",
                        "1",
                        "-",
                    ]
                else:
                    cmd = [
                        "ffmpeg",
                        "-hide_banner",
                        "-nostdin",
                        "-loglevel",
                        "warning",
                        "-i",
                        self.monitor["URL"],
                        "-f",
                        "f32le",
                        "-acodec",
                        "pcm_f32le",
                        "-ar",
                        "24000",
                        "-ac",
                        "1",
                        "-",
                    ]
            except FileNotFoundError:
                Utilities.autoPrint(
                        text=f"Cannot detect system OS. Try again later...",
                        classType="DECODER",
                        severity=severity.warning,
                    )
        elif self.monitor["Type"] == "Radio":
            pass
        else:
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-nostdin",
                "-loglevel",
                "warning",
                "-i",
                self.monitor["URL"],
                "-f",
                "f32le",
                "-acodec",
                "pcm_f32le",
                "-ar",
                "24000",
                "-ac",
                "1",
                "-",
            ]
        self.stream = Popen(
            cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE, bufsize=1
        )
        AlertAudio = empty(0, dtype=int16)
        testStatus = False
        setLevel = 5  # Number of decodes before we count it.
        hold = 3  # Number of samples to hold for
        ATTNTemp = setLevel
        ATTNTemp2 = hold
        ATTNDetected = False
        ATTNActive = False
        window = blackman(2400)
        audioBork = 0
        ATTNOof = False
        while self.run:
            try:
                if not self.monitor["State"]:
                    sleep(1)
                elif not self.monitor["Online"]:
                    self.stream = Popen(
                        cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE, bufsize=1
                    )
                    data = self.stream.stdout.read(
                        24000
                    )  # Try to read 1 second of audio from the stream
                    audio_samples = frombuffer(data, dtype=float32)
                    if len(audio_samples) > 0:
                        Utilities.autoPrint(
                            text=f"Monitor {self.monitorName}: has been restored (Down for {(audioBork-24000)*10} seconds).",
                            classType="MONITOR",
                            severity=severity.info,
                        )
                        audioBork = 0
                        self.monitor["Online"] = True
                    else:
                        audioBork += 1
                        for i in range(10):
                            if self.run:
                                sleep(1)
                            else:
                                break
                else:
                    data = self.stream.stdout.read(2400 * 4)
                    audio_samples = frombuffer(data, dtype=float32)
                    audio_samples_16 = (
                        (audio_samples / 1.414) * 32767
                    ).astype(int16)
                    self.decode.stdin.write(audio_samples_16)
                    ## TODO: EAN Handling to go here.
                    if self.monitor["Alert"] == True:
                        testStatus = True
                        frequencies = self.ATTNDetection(
                            pkt=audio_samples,
                            bufferSize=2400,
                            sampleRate=24000,
                            window=window,
                        )
                        if frequencies:
                            if not ATTNDetected:
                                if ATTNTemp <= 0:
                                    ATTNDetected = True
                                else:
                                    ATTNTemp -= 1
                        else:
                            if ATTNDetected:
                                if ATTNTemp2 <= 0:
                                    ATTNDetected = False
                                    ATTNTemp = setLevel
                                    ATTNTemp2 = hold
                                else:
                                    ATTNTemp2 -= 1
                        if ATTNDetected:
                            if not ATTNActive:
                                Utilities.autoPrint(
                                    text=f"Monitor {self.monitorName}: Attention Tone Detected. Stopping Recording.",
                                    classType="MONITOR",
                                    severity=severity.info,
                                )
                                AlertAudio = AlertAudio[: -(2400 * 6)]
                                self.monitor["AttentionTone"] = True
                                ATTNActive = True
                                ATTNOof = True
                        else:
                            if ATTNActive:
                                Utilities.autoPrint(
                                    text=f"Monitor {self.monitorName}: Attention Tone Ended.",
                                    classType="MONITOR",
                                    severity=severity.info,
                                )
                                self.monitor["AttentionTone"] = False
                                ATTNActive = False
                            if not len(AlertAudio) / 24000 > 120:
                                AlertAudio = append(
                                    AlertAudio,
                                    ((audio_samples / 1.414) * 32767).astype(
                                        int16
                                    ),
                                )
                            else:
                                Utilities.autoPrint(
                                    text=f"Monitor {self.monitorName}: 120 Seconds reached, forcing End of Recording.",
                                    classType="MONITOR",
                                    severity=severity.info,
                                )
                                self.monitor["Alert"] = False
                    elif testStatus == True:
                        testStatus = False
                        Utilities.autoPrint(
                            text=f"Monitor {self.monitorName}: Ending alert Recording.",
                            classType="MONITOR",
                            severity=severity.info,
                        )
                        # alertCallSign = self.AlertData['From'] # changed
                        alertCallSign = EndecManager.config["Callsign"]
                        if len(alertCallSign) == 1:
                            alertCallSign = alertCallSign+'       '
                        elif len(alertCallSign) == 2:
                            alertCallSign = alertCallSign+'      '
                        elif len(alertCallSign) == 3:
                            alertCallSign = alertCallSign+'     '
                        elif len(alertCallSign) == 4:
                            alertCallSign = alertCallSign+'    '
                        elif len(alertCallSign) == 5:
                            alertCallSign = alertCallSign+'   '
                        elif len(alertCallSign) == 6:
                            alertCallSign = alertCallSign+'  '
                        elif len(alertCallSign) == 7:
                            alertCallSign = alertCallSign+' '
                        elif len(alertCallSign) == 8:
                            alertCallSign = alertCallSign
                        else:
                            print('[RELAY] CALLSIGN TOO LONG! Setting to default.')
                            alertCallSign = 'EASDCODR'

                        header = f"{self.AlertData['Protocol']}{alertCallSign}-"
                        EASData = EAS2Text(header)
                        AlertAudio = normalize(
                            AudioSegment(
                                AlertAudio.tobytes(),
                                frame_rate=24000,
                                sample_width=2,
                                channels=1,
                            )[:-685],
                            headroom=0.1,
                        )
                        if EASData.evnt == "RWT":
                            Tone = False
                        else:
                            Tone = ATTNOof
                        Alert = EASGen.genEAS(
                            header=header,
                            attentionTone=Tone,
                            audio=AlertAudio,
                            mode=EndecManager.config["Emulation"],
                        ).set_frame_rate(24000)
                        Utilities.autoPrint(
                            text=f"Audio Message Length: {round(len(AlertAudio)/1000, 2)} Seconds.",
                            classType="MONITOR",
                            severity=severity.info,
                        )
                        Utilities.autoPrint(
                            text=f"Alert Total Length: {round(len(Alert)/1000, 2)} Seconds.",
                            classType="MONITOR",
                            severity=severity.info,
                        )
                        self.AlertData["Length"] = round(len(Alert) / 24000, 2)
                        self.AlertToOld(
                            self.AlertData["Protocol"], self.AlertData
                        )
                        self.RelayManager(self.AlertData, Alert, header)
                        alertName = f"{EndecManager.exportFolder}/EAS_{EASData.org}-{EASData.evnt}-{EASData.timeStamp}-{EASData.callsign.replace('/', '-').strip().replace(' ', '-')}.wav"
                        if EndecManager.logger and EndecManager.export:
                            Alert.export(alertName)
                            self.log = Utilities.log(
                                EndecManager.callsign,
                                EndecManager.webhooks,
                                "Alert Recieved",
                                f"{self.AlertData['Protocol']}{self.AlertData['From']}-",
                                self.AlertData["Filter"]["Name"],
                                self.monitorName,
                                True,
                                alertName,
                                self.monitor["URL"],
                                EndecManager.version,
                                self.log,
                                notification=EndecManager.notification,
                                email=EndecManager.email,
                            )
                            # with open('alertCall.txt', 'w+') as f:
                            #     f.write(f"[{self.AlertData['From']}]")
                        elif EndecManager.logger:
                            self.log = Utilities.log(
                                EndecManager.callsign,
                                EndecManager.webhooks,
                                "Alert Recieved",
                                f"{self.AlertData['Protocol']}{self.AlertData['From']}-",
                                self.AlertData["Filter"]["Name"],
                                self.monitorName,
                                False,
                                "",
                                self.monitor["URL"],
                                EndecManager.version,
                                self.log,
                                notification=EndecManager.notification,
                                email=EndecManager.email,
                            )
                        elif not EndecManager.logger and EndecManager.export:
                            Alert.export(alertName)
                        AlertAudio = empty(0, dtype=int16)
                    else:
                        if len(audio_samples_16) == 0:
                            audioBork += 1
                            if audioBork > 24000:
                                Utilities.autoPrint(
                                    text=f"Monitor {self.monitorName}: Going Offline due to stream error.",
                                    classType="MONITOR",
                                    severity=severity.warning,
                                )
                                self.monitor["Online"] = False
                                self.MonState(update=True)
                        else:
                            audioBork = 0
            except Exception as E:
                if self.run:
                    Utilities.autoPrint(
                        text=f"Monitor {self.monitorName}: {type(E).__name__}, {E}",
                        classType="MONITOR",
                        severity=severity.error,
                    )
                    tb = E.__traceback__
                    while tb is not None:
                        Utilities.autoPrint(
                            text=f"File: {tb.tb_frame.f_code.co_filename}\nFunc: {tb.tb_frame.f_code.co_name}\nLine: {tb.tb_lineno}",
                            classType="MONITOR",
                            severity=severity.error,
                        )
                        tb = tb.tb_next
        Utilities.autoPrint(
            text=f"Monitor {self.monitorName}: Closing Monitor Thread.",
            classType="MONITOR",
            severity=severity.info,
        )
        return

    # @classmethod
    # def PendAlert(cls, Alert, Add: bool):
    #     if Add:
    #         cls.pendingAlerts.append(Alert)
    #     else:
    #         cls.pendingAlerts.remove(Alert)

    def RelayManager(self, AlertData, Alert, header):
        def ALERT_SLEP(Data, filter):
            timeout = int(filter.split(":")[1])
            for i in range(timeout * 60):
                sleep(1)
            if filter.split(":")[0] == "Ignore":
                Utilities.autoPrint(
                    text=f"Ignoring Alert {Event} from {Call}",
                    classType="RELAY",
                    severity=severity.info,
                )
                exit()
            else:
                Utilities.autoPrint(
                    text=f"Sending Alert {Event} from {Call}",
                    classType="RELAY",
                    severity=severity.info,
                )
                CurrentAlert.append(Data)
                exit()

        dothedo = AlertData["Filter"]["Actions"]
        Event = AlertData["Event"]
        Call = AlertData["From"]
        Data = {
            "Audio": Alert,
            "Type": "Alert",
            "Event": Event,
            "Callsign": Call,
            "Protocol": header,
        }
        if "Now" in dothedo:
            Utilities.autoPrint(
                text=f"Sending Alert {Event} from {Call}",
                classType="RELAY",
                severity=severity.info,
            )
            CurrentAlert.append(Data)
        else:
            Utilities.autoPrint(
                text=f"Waiting for {dothedo.split(':')[1]} minutes > Alert {Event} from {Call}",
                classType="RELAY",
                severity=severity.info,
            )
            t = Thread(
                target=ALERT_SLEP,
                name=f"Relay-{self.monitorName}",
                args=(
                    Data,
                    dothedo,
                ),
                daemon=True,
            )
            t.start()
        return


class EndecManager:

    global CurrentAlert
    version = "0.1.50"
    monitors = []
    run = True
    playback = False
    config = None
    configFile = ".config"
    localFIPS = []
    speaker = False
    callsign = "ACRN/SFT"
    Playout = False
    IcecastPlayout = False
    player = None
    icePlayer = None
    leadIn = AudioSegment.empty()
    leadOut = AudioSegment.empty()
    samplerate = 24000
    channels = 1
    logger = False
    webhooks = []
    email = False
    notification = False
    export = False
    exportFolder = ""
    filters = []
    startTime = 0
    weeklyTime = 0
    Tone = AudioSegment.empty()
    AlertCount = 0
    OverrideCount = 0
    CapCount = 0
    MessageCount = 0

    @classmethod
    def addCount(cls, type):
        if type == "Override":
            cls.OverrideCount += 1
        elif type == "CAP":
            cls.CapCount += 1
        elif type == "Alert":
            cls.AlertCount += 1
        cls.MessageCount += 1

    @classmethod
    def setConfig(cls, config, configFile):
        cls.config = config
        cls.configFile = configFile

    @classmethod
    def setCallsign(cls):
        if len(cls.config["Callsign"]) <= 8:
            cls.callsign = cls.config["Callsign"].ljust(8, " ")
        else:
            Utilities.autoPrint(
                text="Callsign too long. Trimming...",
                classType="ENDEC",
                severity=severity.info,
            )
            cls.callsign = cls.config["Callsign"][:8]

    @classmethod
    def setSpeaker(cls):
        cls.Tone = cls.config["PlayoutManager"]["Tone"]
        cls.speaker = cls.config["Speaker"]

    @classmethod
    def setLocalFIPS(
        cls,
    ):
        cls.localFIPS = cls.config["LocalFIPS"]

    @classmethod
    def setSamplerate(cls):
        cls.samplerate = cls.config["PlayoutManager"]["SampleRate"]

    @classmethod
    def setChannels(cls):
        cls.channels = cls.config["PlayoutManager"]["Channels"]

    @classmethod
    def setLogger(cls):
        cls.logger = cls.config["Logger"]["Enabled"]
        cls.webhooks = cls.config["Logger"]["Webhooks"]

    @classmethod
    def setEmail(cls):
        if cls.config["Logger"]["Email"]["Enabled"]:
            cls.email = cls.config["Logger"]["Email"]
        else:
            cls.email = False

    @classmethod
    def setNotification(cls):
        cls.notification = cls.config["Logger"]["Notification"]

    @classmethod
    def setExport(cls):
        cls.export = cls.config["PlayoutManager"]["Export"]["Enabled"]
        cls.exportFolder = cls.config["PlayoutManager"]["Export"]["Folder"]

    @classmethod
    def setFilters(cls):
        cls.filters = cls.config["Filters"]

    @classmethod
    def setPlayout(cls):
        cls.Playout = cls.config["PlayoutManager"]["Audio"]

    @classmethod
    def setIcePlayout(cls):
        cls.IcecastPlayout = cls.config["PlayoutManager"]["Icecast"]["Enabled"]
        cls.IcecastServer = cls.config["PlayoutManager"]["Icecast"]

    @classmethod
    def setPlayer(cls):
        Utilities.autoPrint(
            text="Creating Playout (Audio)",
            classType="PLAYOUT",
            severity=severity.info,
        )
        cls.player = PyAudio().open(
            format=paInt16,
            channels=cls.channels,
            rate=cls.samplerate,
            output=True,
        )

    @classmethod
    def killIcePlayer(cls):
        if cls.icePlayer != None:
            cls.icePlayer.kill()
            sleep(1)
            cls.icePlayer = None

    @classmethod
    def setIcePlayer(cls):
        Utilities.autoPrint(
            text="Creating Playout (Icecast)",
            classType="PLAYOUT",
            severity=severity.info,
        )
        cls.icePlayer = Popen(
            [
                "ffmpeg",
                "-re",
                "-hide_banner",
                "-loglevel",
                "warning",
                "-f",
                "s16le",
                "-ac",
                f"{cls.config['PlayoutManager']['Channels']}",
                "-ar",
                f"{cls.config['PlayoutManager']['SampleRate']}",
                "-i",
                "-",
                "-ab",
                cls.IcecastServer["Bitrate"],
                "-acodec",
                "libmp3lame",
                "-content_type",
                "audio/mpeg",
                "-f",
                "mp3",
                "-ice_name",
                f'"{cls.callsign} - ASMARA TECHNOLOGIES ENDEC"',
                f"icecast://{cls.IcecastServer['Source']}:{cls.IcecastServer['Pass']}@{cls.IcecastServer['Address']}:{cls.IcecastServer['Port']}/{cls.IcecastServer['Mountpoint']}",
            ],
            stdin=PIPE,
            stdout=PIPE,
            stderr=PIPE,
        )

    @classmethod
    def setLeadIn(cls):
        if cls.config["PlayoutManager"]["LeadIn"]["Enabled"]:
            file = cls.config["PlayoutManager"]["LeadIn"]["File"]
            type = cls.config["PlayoutManager"]["LeadIn"]["Type"]
            cls.leadIn = AudioSegment.silent(500) + AudioSegment.from_file(
                file=file, format=type
            ).set_frame_rate(cls.samplerate).set_sample_width(2).set_channels(
                1
            )

    @classmethod
    def setLeadOut(cls):
        if cls.config["PlayoutManager"]["LeadOut"]["Enabled"]:
            file = cls.config["PlayoutManager"]["LeadOut"]["File"]
            type = cls.config["PlayoutManager"]["LeadOut"]["Type"]
            cls.leadOut = AudioSegment.from_file(
                file=file, format=type
            ).set_frame_rate(cls.samplerate).set_sample_width(2).set_channels(
                1
            ) + AudioSegment.silent(
                500
            )

    def loadLogs(self):
        try:
            with open(".log", "r") as f:
                Utilities.autoPrint(
                    text=f"Loading '.log' to Alert Database",
                    classType="ENDEC",
                    severity=severity.info,
                )
                logFile = load(f)
            try:
                key = list(logFile[self.callsign]["Alerts"].keys())
                for index in range(len(key[-10:])):
                    k = key[index]
                    v = logFile[self.callsign]["Alerts"][k]
                    EndecMon.AlertToOld(k, v)
                Utilities.autoPrint(
                    text="Done loading alert database",
                    classType="ENDEC",
                    severity=severity.info,
                )
            except KeyError:
                Utilities.autoPrint(
                    text="Failed to load alert database",
                    classType="ENDEC",
                    severity=severity.error,
                )
                logFile[self.callsign] = {}
                logFile[self.callsign]["Alerts"] = {}
                logFile[self.callsign]["Weekly"] = {"Timestamp": 0}
                with open(".log", "w") as f:
                    dump(logFile, f, indent=4)
        except FileNotFoundError:
            Utilities.autoPrint(
                text="Creating Log File to '.log'",
                classType="ENDEC",
                severity=severity.info,
            )
            with open(".log", "w") as f:
                var = {self.callsign: {"Alerts": {}, "Weekly": {"Timestamp": 0}}}
                dump(var, f, indent=4)

    def makeConfig(self):
        Utilities.autoPrint(
            text="New Config Made, please configure it properly before use.",
            classType="ENDEC",
            severity=severity.info,
        )
        ## TODO: Simple Initial Config Setup Script

    @classmethod
    def randomWeeklyAlertGen(cls):
        Utilities.autoPrint(
            text="Generating Automated RWT...",
            classType="GENERATOR",
            severity=severity.info,
        )
        noCall = f"ZCZC-EAS-RWT-{'-'.join(cls.localFIPS)}+0015-{DT.utcnow().strftime('%j%H%M')}-"
        # with open('alertCall.txt', 'r') as f:
        #     alertCallSign = f.read().replace('[', '').replace(']', '')

        alertCallSign = EndecManager.config["Callsign"]
        if len(alertCallSign) == 1:
            alertCallSign = alertCallSign+'       '
        elif len(alertCallSign) == 2:
            alertCallSign = alertCallSign+'      '
        elif len(alertCallSign) == 3:
            alertCallSign = alertCallSign+'     '
        elif len(alertCallSign) == 4:
            alertCallSign = alertCallSign+'    '
        elif len(alertCallSign) == 5:
            alertCallSign = alertCallSign+'   '
        elif len(alertCallSign) == 6:
            alertCallSign = alertCallSign+'  '
        elif len(alertCallSign) == 7:
            alertCallSign = alertCallSign+' '
        elif len(alertCallSign) == 8:
            alertCallSign = alertCallSign
        else:
            print('[RELAY] CALLSIGN TOO LONG! Setting to default.')
            alertCallSign = 'EASDCODR'
        ALRT = f"{noCall}{alertCallSign}-"
        EASData = EAS2Text(ALRT)
        Headers = EASGen.genEAS(
            header=ALRT,
            attentionTone=False,
            mode=cls.config["Emulation"],
        ).set_frame_rate(cls.samplerate)
        alertName = f"{cls.exportFolder}/EAS_{EASData.org}-{EASData.evnt}-{EASData.timeStamp}-{EASData.callsign.replace('/', '-').strip().replace(' ', '-')}.wav"
        if cls.export:
            Headers.export(alertName)
        AlertData = {
            "Monitor": "AlertGen",
            "Time": mktime(DT.utcnow().timetuple()),
            "Event": " ".join(EASData.evntText.split(" ")[1:]),
            "Protocol": noCall,
            "From": EASData.callsign,
            "Filter": {
                "Matched": True,
                "Name": "AlertGen",
                "Actions": "Relay:Now",
            },
            "Length": (len(Headers) / 1000),
        }
        Utilities.autoPrint(
            text=f"Sending Alert:\n{EASData.EASText}\n{ALRT}",
            classType="GENERATOR",
            severity=severity.info,
        )
        if cls.logger and cls.export:
            cls.log = Utilities.log(
                cls.callsign,
                cls.webhooks,
                "Automatic Weekly Generated",
                ALRT,
                "",
                "",
                True,
                alertName,
                "",
                cls.version,
                notification=EndecManager.notification,
                email=EndecManager.email,
            )
        elif cls.logger:
            cls.log = Utilities.log(
                cls.callsign,
                cls.webhooks,
                "Automatic Weekly Generated",
                ALRT,
                "",
                "",
                False,
                "",
                "",
                cls.version,
                notification=EndecManager.notification,
                email=EndecManager.email,
            )
        EndecMon.AlertToOld(noCall, AlertData)
        CurrentAlert.append(
            {
                "Audio": Headers,
                "Event": " ".join(EASData.evntText.split(" ")[1:]),
                "Callsign": EASData.callsign,
                "Type": "Alert",
                "Protocol": ALRT,
            }
        )

    @classmethod
    def systemStartup(cls):
        cls.startTime = DT.now().replace(microsecond=0).timestamp()
        with open(".log", "r+") as f:
            logFile = load(f)
            if logFile[cls.callsign]["Weekly"]["Timestamp"] != 0:
                if (
                    logFile[cls.callsign]["Weekly"]["Timestamp"]
                    - cls.startTime
                    >= 0
                ):
                    cls.weeklyTime = Utilities.genRandomWeekly(cls.weeklyTime)
                    logFile[cls.callsign]["Weekly"][
                        "Timestamp"
                    ] = cls.weeklyTime
                else:
                    cls.weeklyTime = logFile[cls.callsign]["Weekly"][
                        "Timestamp"
                    ]
                    return
            else:
                cls.weeklyTime = Utilities.genRandomWeekly()
                logFile[cls.callsign]["Weekly"]["Timestamp"] = cls.weeklyTime
            f.seek(0)
            dump(logFile, f, indent=4)

    @classmethod
    def RandomRWT(cls):
        while cls.run:
            now = DT.now().replace(microsecond=0).timestamp()
            if now >= cls.weeklyTime:
                weeklyOof = cls.weeklyTime
                with open(".log", "r+") as f:
                    logFile = load(f)
                    cls.weeklyTime = Utilities.genRandomWeekly(weeklyOof)
                    logFile[cls.callsign]["Weekly"][
                        "Timestamp"
                    ] = cls.weeklyTime
                    f.seek(0)
                    dump(logFile, f, indent=4)
            sleep(1)

    @classmethod
    def setTone(cls):
        cls.Tone = cls.config["PlayoutManager"]["Tone"]

    def loadConfig(self):
        self.setPlayout()
        self.setIcePlayout()
        self.setCallsign()
        self.setSpeaker()
        self.setLocalFIPS()
        self.setLeadIn()
        self.setLeadOut()
        self.setSamplerate()
        self.setChannels()
        self.setLogger()
        self.setEmail()
        self.setNotification()
        self.setExport()
        self.setFilters()
        self.loadLogs()
        self.systemStartup()
        self.setTone()
        self.weekyThread = Thread(
            target=self.RandomRWT, name="WeeklyManager", daemon=True
        )

    @classmethod
    def changeState(cls):
        cls.run = True

    @classmethod
    def changeState(cls):
        cls.run = True

    def __init__(self, configFile) -> None:
        if self.run != True:
            self.changeState()
        try:
            with open(configFile, "r") as f:
                self.setConfig(load(f), configFile)
        except FileNotFoundError:
            Utilities.autoPrint(
                text="Config file has been removed, or does not exist. Writing the default config file to '.config'",
                classType="ENDEC",
                severity=severity.info,
            )
            try:
                Utilities.WriteDefConfig()
                with open(".config", "r") as f:
                    self.setConfig(load(f), ".config")
                self.makeConfig()
            except FileNotFoundError or PermissionError:
                Utilities.autoPrint(
                    text="*** FATAL ERROR, CANNOT READ OR WRITE CONFIG FILE. CLOSING... ***",
                    classType="ENDEC",
                    severity=severity.info,
                )
                exit(1)
        self.loadConfig()
        self.log = ""
        self.lastAlert = {
            "Audio": AudioSegment.empty(),
            "Event": "",
            "Type": "",
            "Protocol": "",
        }
        self.AlertAvailable = False
        self.nowPlaying = self.config["PlayoutManager"]["Icecast"][
            "WaitingStatus"
        ]
        self.nowPlayingData = AudioSegment.empty()
        self.nowPlayingTS = 0
        EndecMon.run = True
        self.AlertManager = Thread(
            target=self.AlertCountManager, name="AlertManager", daemon=True
        )
        self.PlayoutManager = Thread(
            target=self.playout, name="PlayoutManager", daemon=True
        )
        self.PlayoutManager2 = Thread(
            target=self.playoutManager2, name="FileManager", daemon=True
        )
        self.DJ = Thread(target=self.autoDJ, name="AutoDJ", daemon=True)
        self.OverrideManager = Thread(
            target=self.overrideManager, name="OverrideManager", daemon=True
        )
        Utilities.autoPrint(
            text="Creating AlertManager.",
            classType="ENDEC",
            severity=severity.info,
        )
        self.AlertManager.start()
        Utilities.autoPrint(
            text="Creating PlayoutManager.",
            classType="ENDEC",
            severity=severity.info,
        )
        self.PlayoutManager.start()
        self.PlayoutManager2.start()
        if self.config["PlayoutManager"]["AutoDJ"]["Enabled"]:
            Utilities.autoPrint(
                text="Creating AutoDJ.",
                classType="ENDEC",
                severity=severity.info,
            )
            self.DJ.start()
        if self.config["PlayoutManager"]["Override"]["Enabled"]:
            Utilities.autoPrint(
                text="Creating OverrideManager.",
                classType="ENDEC",
                severity=severity.info,
            )
            self.OverrideManager.start()
        for monitor in self.config["Monitors"]:
            self.monitors.append(EndecMon(monitor))

    @classmethod
    def killMonitors(cls):
        Utilities.autoPrint(
            text=f"Killing Monitors...",
            classType="MANAGER",
            severity=severity.info,
        )
        EndecMon.run = False
        for monitor in cls.monitors:
            monitor.killMon()
        EndecMon.monitors.clear()
        cls.monitors.clear()

    @classmethod
    def KillEndec(cls):
        if EndecMon.run:
            cls.killMonitors()
        cls.IcecastPlayout = False
        cls.Playout = False
        Utilities.autoPrint(
            text=f"Killing Playout Services...",
            classType="MANAGER",
            severity=severity.info,
        )
        cls.run = False
        cls.player = None
        cls.killIcePlayer()
        print("ENDEC Killed. Waiting for all services to end...")
        sleep(5)
        print("====================================\n\n")
        return

    def AlertFileDump(self, alerts: list = []):
        if len(alerts) == 0:
            pass
        else:
            with open(".log", "r+") as f:
                log = load(f)
                for alert in alerts:
                    log[self.callsign]["Alerts"].update(alert)
                f.seek(0)
                dump(log, f, indent=4)
        return

    def AlertCountManager(self):
        alerts = []
        while self.run:
            if len(EndecMon.receivedAlertsIndex) > 50:
                Utilities.autoPrint(
                    text=f"Clearing up oldest 10 alerts...",
                    classType="MANAGER",
                    severity=severity.info,
                )
                while len(EndecMon.receivedAlertsIndex) > 40:
                    alerts.append(EndecMon.AlertFromOld(0))
                self.AlertFileDump(alerts=alerts)
                alerts = []
                Utilities.autoPrint(
                    text=f"Done.", classType="MANAGER", severity=severity.info
                )
            else:
                pass
            i = 60
            while self.run and i != 0:
                sleep(1)
                i -= 1
        Utilities.autoPrint(
            text="Dumping Old Alerts...",
            classType="MANAGER",
            severity=severity.info,
        )
        alerts = []
        for alert in EndecMon.receivedAlertsIndex:
            alerts.append(EndecMon.AlertFromOld(0))
        self.AlertFileDump(alerts=alerts)

    def overrideManager(self):
        while self.run:
            sleep(0.5)  # High number because Low Prio
            overrideFolder = self.config["PlayoutManager"]["Override"][
                "Folder"
            ]
            if not overrideFolder.startswith(
                "/"
            ) or not overrideFolder.startswith("C:/"):
                overrideFolder = (
                    getcwd()
                    + "/"
                    + self.config["PlayoutManager"]["Override"]["Folder"]
                )
            for r, d, files in walk(overrideFolder):
                for file in files:
                    if file.lower() == "holdplacer":
                        pass
                    elif file.lower().endswith(".wav"):
                        sleep(1)  # High number because Low Prio
                        Utilities.autoPrint(
                            text=f"Adding file {str(file)} to Playout System.",
                            classType="OVERRIDE",
                            severity=severity.info,
                        )
                        ALERT = {
                            "Audio": AudioSegment.silent(500)
                            + AudioSegment.from_wav(path.join(r, file))
                            .set_frame_rate(self.samplerate)
                            .set_sample_width(2)
                            .set_channels(1)
                            + AudioSegment.silent(500),
                            "Type": "Override",
                            "Protocol": file,
                        }
                        if self.export:
                            ALERT["Audio"].export(
                                f"{self.exportFolder}/OVERRIDE_{file.split('.')[0]}.wav",
                                format="wav",
                            )
                        CurrentAlert.append(ALERT)
                        remove(path.join(r, file))
                    elif file.lower().endswith(".mp3"):
                        sleep(1)  # High number because Low Prio
                        try:
                            test = mediainfo(path.join(r, file))
                            try:
                                art = test["TAG"]["artist"]
                                com = test["TAG"]["comments"]
                            except KeyError:
                                sleep(5)
                                test = mediainfo(path.join(r, file))
                                art = test["TAG"]["artist"]
                                com = test["TAG"]["comments"]
                            if art == "capdec":
                                EASData = EAS2Text(com)
                                ALERT = {
                                    "Audio": AudioSegment.silent(500)
                                    + AudioSegment.from_mp3(path.join(r, file))
                                    .set_frame_rate(self.samplerate)
                                    .set_sample_width(2)
                                    .set_channels(1)
                                    + AudioSegment.silent(500),
                                    "Event": " ".join(
                                        EASData.evntText.split(" ")[1:]
                                    ),
                                    "Callsign": "CAPDEC",
                                    "Type": "CAP",
                                    "Protocol": com,
                                }
                                noCall = "-".join(com.split("-")[:-2]) + "-"
                                if not noCall in EndecMon.receivedAlerts:
                                    Utilities.autoPrint(
                                        text="Adding CAP Alert to Playout System.",
                                        classType="OVERRIDE",
                                        severity=severity.info,
                                    )
                                    if self.export:
                                        ALERT["Audio"].export(
                                            f"{self.exportFolder}/EAS_CAP-{EASData.org}-{EASData.evnt}-{EASData.timeStamp}-CAPDEC.wav"
                                        )
                                    AlertData = {
                                        "Monitor": "CAP",
                                        "Time": mktime(
                                            DT.utcnow().timetuple()
                                        ),
                                        "Event": " ".join(
                                            EASData.evntText.split(" ")[1:]
                                        ),
                                        "Protocol": noCall,
                                        "From": EASData.callsign,
                                        "Filter": {
                                            "Matched": True,
                                            "Name": "CAPDEC",
                                            "Actions": "Relay:Now",
                                        },
                                        "Length": (len(ALERT["Audio"]) / 1000),
                                    }
                                    self.lastAlert = ALERT
                                    EndecMon.AlertToOld(com, AlertData)
                                    if self.logger and self.export:
                                        self.log = Utilities.log(
                                            self.callsign,
                                            self.webhooks,
                                            "CAP Alert Sent",
                                            com,
                                            "",
                                            "",
                                            True,
                                            f"{self.exportFolder}/EAS_CAP-{EASData.org}-{EASData.evnt}-{EASData.timeStamp}-CAPDEC.wav",
                                            "",
                                            self.version,
                                            notification=EndecManager.notification,
                                            email=EndecManager.email,
                                        )
                                    elif self.logger:
                                        self.log = Utilities.log(
                                            self.callsign,
                                            self.webhooks,
                                            "CAP Alert Sent",
                                            com,
                                            "",
                                            "",
                                            False,
                                            "",
                                            "",
                                            self.version,
                                            notification=EndecManager.notification,
                                            email=EndecManager.email,
                                        )
                                    CurrentAlert.append(ALERT)
                                else:
                                    Utilities.autoPrint(
                                        text="CAP Alert already sent.",
                                        classType="OVERRIDE",
                                        severity=severity.info,
                                    )
                            else:
                                Utilities.autoPrint(
                                    text=f"Adding file {str(file)} to Playout System.",
                                    classType="OVERRIDE",
                                    severity=severity.info,
                                )
                                ALERT = {
                                    "Audio": AudioSegment.silent(500)
                                    + AudioSegment.from_mp3(path.join(r, file))
                                    .set_frame_rate(self.samplerate)
                                    .set_sample_width(2)
                                    .set_channels(1)
                                    + AudioSegment.silent(500),
                                    "Type": "Override",
                                    "Protocol": file,
                                }
                                if self.export:
                                    ALERT["Audio"].export(
                                        f"{self.exportFolder}/OVERRIDE_{file.split('.')[0]}.wav",
                                        format="wav",
                                    )
                                CurrentAlert.append(ALERT)
                        except Exception as E:
                            Utilities.autoPrint(
                                text=f"{type(E).__name__}, {E}",
                                classType="OVERRIDE",
                                severity=severity.error,
                            )
                            tb = E.__traceback__
                            while tb is not None:
                                Utilities.autoPrint(
                                    text=f"File: {tb.tb_frame.f_code.co_filename}\nFunc: {tb.tb_frame.f_code.co_name}\nLine: {tb.tb_lineno}",
                                    classType="OVERRIDE",
                                    severity=severity.error,
                                )
                                tb = tb.tb_next
                        remove(path.join(r, file))
                    else:
                        Utilities.autoPrint(
                            text=f"[OVERRIDE] File {file} is not a WAV, MP3, FLV, or OGG file.",
                            classType="OVERRIDE",
                            severity=severity.info,
                        )
                        remove(path.join(r, file))

    def playoutManager2(self):
        global CurrentAlert
        while self.run:
            if len(CurrentAlert) != 0:
                if self.IcecastPlayout or self.Playout or self.speaker:
                    self.AlertAvailable = True
                else:
                    CurrentAlert.pop(0)
                    Utilities.autoPrint(
                        text="Disposing Alert Audio",
                        classType="PLAYOUT",
                        severity=severity.info,
                    )
            else:
                pass
            sleep(0.25)

    def autoDJ(self):
        SilentPatch = AudioSegment.silent(250)
        while self.run:
            musicList = []
            idList = []
            songsPlayed = 0
            for r, d, files in walk(
                getcwd()
                + "/"
                + self.config["PlayoutManager"]["AutoDJ"]["Folder"]
            ):
                for file in files:
                    if not self.run:
                        return
                    if file.endswith("mp3") or file.endswith("wav"):
                        musicList.append(r + "/" + file)
            for r, d, files in walk(
                getcwd()
                + "/"
                + self.config["PlayoutManager"]["AutoDJ"]["IDFolder"]
            ):
                for file in files:
                    if not self.run:
                        return
                    if file.endswith("mp3") or file.endswith("wav"):
                        idList.append(r + "/" + file)
            if len(musicList) == 0:
                self.nowPlayingTS = 0
                self.nowPlaying = ""
                self.nowPlayingData = AudioSegment.empty()
                self.nowPlaying = self.config["PlayoutManager"]["Icecast"][
                    "WaitingStatus"
                ]
                if self.Tone:
                    self.nowPlayingData = Sine(3000).to_audio_segment(
                        duration=1000, volume=-2
                    )
                else:
                    self.nowPlayingData = AudioSegment.silent(3000)
                for sec in range(4 * 3):
                    if not self.run:
                        return
                    self.nowPlayingTS += 250
                    sleep(0.25)
            else:
                shuffle(musicList)
                while len(musicList) > 0:
                    if songsPlayed == 0:
                        if len(idList) != 0:
                            try:
                                self.nowPlayingTS = 0
                                self.nowPlaying = ""
                                self.nowPlayingData = AudioSegment.empty()
                                song = choice(idList)
                                if song.endswith("mp3"):
                                    songData = (
                                        AudioSegment.from_mp3(song)
                                        .set_frame_rate(
                                            frame_rate=self.samplerate
                                        )
                                        .set_channels(self.channels)
                                        .set_sample_width(2)
                                    )
                                elif song.endswith("wav"):
                                    songData = (
                                        AudioSegment.from_wav(song)
                                        .set_frame_rate(
                                            frame_rate=self.samplerate
                                        )
                                        .set_channels(self.channels)
                                        .set_sample_width(2)
                                    )
                                self.nowPlaying = (
                                    f"{self.callsign.strip()} IP Radio"
                                )
                                self.nowPlayingData = (
                                    AudioSegment.silent(250)
                                    + songData
                                    + AudioSegment.silent(250)
                                )
                                for sec in range(
                                    int(len(songData) / 1000) * 4
                                ):
                                    if not self.run:
                                        return
                                    self.nowPlayingTS += 250
                                    sleep(0.25)
                                songsPlayed = self.config["PlayoutManager"][
                                    "AutoDJ"
                                ]["IDSongs"]
                            except FileNotFoundError:
                                idList.remove(song)
                                continue
                    try:
                        self.nowPlayingTS = 0
                        self.nowPlaying = ""
                        self.nowPlayingData = AudioSegment.empty()
                        song = choice(musicList)
                        musicList.remove(song)
                        if song.endswith("mp3"):
                            songData = (
                                AudioSegment.from_mp3(song)
                                .set_frame_rate(frame_rate=self.samplerate)
                                .set_channels(self.channels)
                                .set_sample_width(2)
                            )
                        elif song.endswith("wav"):
                            songData = (
                                AudioSegment.from_wav(song)
                                .set_frame_rate(frame_rate=self.samplerate)
                                .set_channels(self.channels)
                                .set_sample_width(2)
                            )
                        try:
                            test = mediainfo(song)
                            title = test["TAG"]["title"]
                            artist = test["TAG"]["artist"]
                            self.nowPlaying = f"{title} - {artist}"
                        except:
                            self.nowPlaying = ".".join(
                                song.split("/")[-1].split(".")[:1]
                            )
                        self.nowPlayingData = songData
                        for sec in range(int(len(songData) / 1000) * 4):
                            if not self.run:
                                return
                            self.nowPlayingTS += 250
                            sleep(0.25)
                        self.nowPlayingData = SilentPatch
                        self.nowPlayingTS == 0
                        songsPlayed -= 1
                    except FileNotFoundError:
                        musicList.remove(song)
                        continue

    @classmethod
    def makeURLReady(cls, data):
        return (
            data.replace("%", "%25")
            .replace("$", "%24")
            .replace("&", "%26")
            .replace("+", "%2B")
            .replace(",", "%2C")
            .replace("/", "%2F")
            .replace(":", "%eA")
            .replace(";", "%3B")
            .replace("=", "%3D")
            .replace("?", "%3F")
            .replace("@", "%40")
            .replace(" ", "%20")
            .replace('"', "%22")
            .replace("<", "%3C")
            .replace(">", "%3E")
            .replace("#", "%23")
            .replace("{", "%7B")
            .replace("}", "%7D")
            .replace("|", "%7C")
            .replace("\\", "%5C")
            .replace("^", "%5E")
            .replace("~", "%7E")
            .replace("[", "%5B")
            .replace("]", "%5D")
            .replace("`", "%60")
        )

    @classmethod
    def UpdateIcecastNP(cls, server, data):
        get(
            f"http://{server['Address']}:{server['Port']}/admin/metadata?mount=/{server['Mountpoint']}&mode=updinfo&song={cls.makeURLReady(data)}",
            auth=(server["Source"], server["Pass"]),
        )

    def playout(self):
        global CurrentAlert
        iceWorking = False
        if (self.Playout or self.speaker) and self.IcecastPlayout:
            self.setPlayer()  # Will scream in pain
            self.setIcePlayer()
            iceWorking = True
        elif self.Playout or self.speaker:
            self.setPlayer()  # Will scream in pain
        elif self.IcecastPlayout:
            self.setIcePlayer()
            iceWorking = True
        NP = ""
        sleep(1)
        while self.run:
            if not self.AlertAvailable:
                try:
                    if not self.nowPlaying:
                        if self.IcecastPlayout and iceWorking:
                            self.icePlayer.stdin.write(
                                AudioSegment.silent(
                                    duration=250, frame_rate=self.samplerate
                                )._data
                            )
                    else:
                        if self.nowPlaying != NP:
                            Utilities.autoPrint(
                                text=f"Now Playing: {self.nowPlaying}",
                                classType="PLAYOUT",
                                severity=severity.info,
                            )
                            NP = self.nowPlaying
                            if self.IcecastPlayout and iceWorking:
                                self.UpdateIcecastNP(
                                    self.IcecastServer, self.nowPlaying
                                )
                        data = make_chunks(
                            self.nowPlayingData[self.nowPlayingTS :], 250
                        )
                        for chunkyBoi in data:
                            if not self.AlertAvailable:
                                if self.Playout:
                                    self.player.write(chunkyBoi._data)
                                if self.IcecastPlayout:
                                    try:
                                        if iceWorking:
                                            self.icePlayer.stdin.write(
                                                chunkyBoi._data
                                            )
                                        else:
                                            Utilities.autoPrint(
                                                text=f"Trying to restore Icecast...",
                                                classType="PLAYOUT",
                                                severity=severity.info,
                                            )
                                            self.killIcePlayer()
                                            self.setIcePlayer()
                                            sleep(1)
                                            iceWorking = True
                                    except BrokenPipeError as E:
                                        Utilities.autoPrint(
                                            text=f"Icecast Playout Crashed.",
                                            classType="PLAYOUT",
                                            severity=severity.info,
                                        )
                                        iceWorking = False
                                    except Exception as E:
                                        Utilities.autoPrint(
                                            text=f"IC {type(E).__name__}, {E}",
                                            classType="PLAYOUT",
                                            severity=severity.error,
                                        )
                                        tb = E.__traceback__
                                        while tb is not None:
                                            Utilities.autoPrint(
                                                text=f"File: {tb.tb_frame.f_code.co_filename}\nFunc: {tb.tb_frame.f_code.co_name}\nLine: {tb.tb_lineno}",
                                                classType="PLAYOUT",
                                                severity=severity.error,
                                            )
                                            tb = tb.tb_next
                                        iceWorking = False
                except Exception as E:
                    Utilities.autoPrint(
                        text=f"PL {type(E).__name__}, {E}",
                        classType="PLAYOUT",
                        severity=severity.error,
                    )
                    tb = E.__traceback__
                    while tb is not None:
                        Utilities.autoPrint(
                            text=f"File: {tb.tb_frame.f_code.co_filename}\nFunc: {tb.tb_frame.f_code.co_name}\nLine: {tb.tb_lineno}",
                            classType="PLAYOUT",
                            severity=severity.error,
                        )
                        tb = tb.tb_next
            else:
                try:
                    AlertData = CurrentAlert.pop(0)
                    self.addCount(AlertData["Type"])
                    OverrideFile = False
                    if AlertData["Type"] == "Override":
                        OverrideFile = True
                        oof = f"Playing Override File {AlertData['Protocol']}."
                        AlertAudio = (
                            AudioSegment.silent(500)
                            + AlertData["Audio"]
                            + AudioSegment.silent(500)
                        )
                    elif AlertData["Type"] == "CAP":
                        Event = AlertData["Event"]
                        oof = f"Relaying {Event} from CAPDEC."
                        AlertAudio = (
                            AudioSegment.silent(500)
                            + AlertData["Audio"]
                            + AudioSegment.silent(500)
                        )
                    elif AlertData["Type"] == "Alert":
                        self.lastAlert = AlertData
                        Event = AlertData["Event"]
                        Call = AlertData["Callsign"]
                        if self.logger:
                            self.log = Utilities.log(
                                self.callsign,
                                self.webhooks,
                                "Alert Sent",
                                AlertData["Protocol"],
                                "",
                                "",
                                False,
                                "",
                                "",
                                self.version,
                                notification=EndecManager.notification,
                                email=EndecManager.email,
                            )
                        AlertAudio = AlertData["Audio"]
                        oof = f"Relaying {Event} from {Call}."
                    Utilities.autoPrint(
                        text=f"{oof}",
                        classType="PLAYOUT",
                        severity=severity.info,
                    )
                    if self.IcecastPlayout and iceWorking:
                        self.UpdateIcecastNP(self.IcecastServer, oof)
                    self.playback = True
                    AlertAudio = AlertAudio.set_frame_rate(
                        self.samplerate
                    ).set_channels(self.config["PlayoutManager"]["Channels"])
                    data = make_chunks(
                        self.leadIn + AlertAudio + self.leadOut, 500
                    )
                    for chunk in data:
                        if self.Playout or self.speaker:
                            self.player.write(chunk._data)
                        if self.IcecastPlayout and iceWorking:
                            self.icePlayer.stdin.write(chunk._data)
                        if not self.playback:
                            if not OverrideFile:
                                Utilities.autoPrint(
                                    text="Aborting EAS Alert...",
                                    classType="PLAYOUT",
                                    severity=severity.info,
                                )
                                EOM = (
                                    EASGen.genEOM(
                                        mode=self.config["Emulation"]
                                    )
                                    .set_frame_rate(self.samplerate)
                                    .set_channels(
                                        self.config["PlayoutManager"][
                                            "Channels"
                                        ]
                                    )
                                    ._data
                                )
                                if self.Playout or self.speaker:
                                    self.player.write(EOM)
                                if self.IcecastPlayout and iceWorking:
                                    self.icePlayer.stdin.write(EOM)
                            else:
                                Utilities.autoPrint(
                                    text="Aborting Override file...",
                                    classType="PLAYOUT",
                                    severity=severity.info,
                                )
                            break
                    self.playback = False
                    Utilities.autoPrint(
                        text="Finished Playout.",
                        classType="PLAYOUT",
                        severity=severity.info,
                    )
                    if self.IcecastPlayout and iceWorking:
                        self.UpdateIcecastNP(
                            self.IcecastServer, self.nowPlaying
                        )
                    self.AlertAvailable = False
                except Exception as E:
                    Utilities.autoPrint(
                        text=f"AL {type(E).__name__}, {E}",
                        classType="PLAYOUT",
                        severity=severity.error,
                    )
                    tb = E.__traceback__
                    while tb is not None:
                        Utilities.autoPrint(
                            text=f"File: {tb.tb_frame.f_code.co_filename}\nFunc: {tb.tb_frame.f_code.co_name}\nLine: {tb.tb_lineno}",
                            classType="PLAYOUT",
                            severity=severity.error,
                        )
                        tb = tb.tb_next
                    self.AlertAvailable = False
                    if self.IcecastPlayout and iceWorking:
                        self.UpdateIcecastNP(
                            self.IcecastServer, self.nowPlaying
                        )

    ##TODO: Automated responses for Menu Timeouts / Exits / Invalid Options

    def IssueAlert(self):
        Utilities.autoPrint("=== AlertGen ===")
        if self.lastAlert["Audio"] != AudioSegment.empty():
            Utilities.autoPrint(
                f"1) Send RWT\n2) Send DMO\n3) Generate Custom Alert\n4) Relay last alert ({self.lastAlert['Event']} from {self.lastAlert['Callsign'].strip()})\n5) Abort Alert Generation"
            )
        else:
            Utilities.autoPrint(
                f"1) Send RWT\n2) Send DMO\n3) Generate Custom Alert\n4) Relay last alert (NONE)\n5) Abort Alert Generation"
            )
        ap = Utilities.user_input(30, "AlertGen")
        if ap == None:
            Utilities.autoPrint(
                text="Menu Timeout.",
                classType="GENERATOR",
                severity=severity.info,
            )
            Utilities.autoPrint("================")
            return False
        else:
            if ap == "1":
                Utilities.autoPrint(
                    text="Generating RWT...",
                    classType="GENERATOR",
                    severity=severity.info,
                )
                noCall = f"ZCZC-EAS-RWT-{'-'.join(self.localFIPS)}+0015-{DT.utcnow().strftime('%j%H%M')}-"
                ALRT = f"{noCall}{self.callsign}-"
                EASData = EAS2Text(ALRT)
                Headers = EASGen.genEAS(
                    header=ALRT,
                    attentionTone=False,
                    mode=self.config["Emulation"],
                ).set_frame_rate(self.samplerate)
                alertName = f"{self.exportFolder}/EAS_{EASData.org}-{EASData.evnt}-{EASData.timeStamp}-{EASData.callsign.replace('/', '-').strip().replace(' ', '-')}.wav"
                if self.export:
                    Headers.export(alertName)
                AlertData = {
                    "Monitor": "AlertGen",
                    "Time": mktime(DT.utcnow().timetuple()),
                    "Event": " ".join(EASData.evntText.split(" ")[1:]),
                    "Protocol": noCall,
                    "From": EASData.callsign,
                    "Filter": {
                        "Matched": True,
                        "Name": "AlertGen",
                        "Actions": "Relay:Now",
                    },
                    "Length": (len(Headers) / 1000),
                }
                Utilities.autoPrint(
                    text=f"Sending Alert:\n{EASData.EASText}\n{ALRT}",
                    classType="GENERATOR",
                    severity=severity.info,
                )
                if self.logger and self.export:
                    self.log = Utilities.log(
                        self.callsign,
                        self.webhooks,
                        "Local Alert Originated",
                        ALRT,
                        "",
                        "",
                        True,
                        alertName,
                        "",
                        self.version,
                        notification=EndecManager.notification,
                        email=EndecManager.email,
                    )
                elif self.logger:
                    self.log = Utilities.log(
                        self.callsign,
                        self.webhooks,
                        "Local Alert Originated",
                        ALRT,
                        "",
                        "",
                        False,
                        "",
                        "",
                        self.version,
                        notification=EndecManager.notification,
                        email=EndecManager.email,
                    )
                EndecMon.AlertToOld(noCall, AlertData)
                CurrentAlert.append(
                    {
                        "Audio": Headers,
                        "Event": " ".join(EASData.evntText.split(" ")[1:]),
                        "Callsign": EASData.callsign,
                        "Type": "Alert",
                        "Protocol": ALRT,
                    }
                )
            elif ap == "2":
                Utilities.autoPrint(
                    text="Generating DMO...",
                    classType="GENERATOR",
                    severity=severity.info,
                )
                noCall = f"ZCZC-EAS-DMO-{'-'.join(self.localFIPS)}+0015-{DT.utcnow().strftime('%j%H%M')}-"
                ALRT = f"{noCall}{self.callsign}-"
                EASData = EAS2Text(ALRT)
                Headers = EASGen.genEAS(
                    header=ALRT,
                    attentionTone=False,
                    mode=self.config["Emulation"],
                ).set_frame_rate(self.samplerate)
                alertName = f"{self.exportFolder}/EAS_{EASData.org}-{EASData.evnt}-{EASData.timeStamp}-{EASData.callsign.replace('/', '-').strip().replace(' ', '-')}.wav"
                if self.export:
                    Headers.export(alertName)
                AlertData = {
                    "Monitor": "AlertGen",
                    "Time": mktime(DT.utcnow().timetuple()),
                    "Event": " ".join(EASData.evntText.split(" ")[1:]),
                    "Protocol": noCall,
                    "From": EASData.callsign,
                    "Filter": {
                        "Matched": True,
                        "Name": "AlertGen",
                        "Actions": "Relay:Now",
                    },
                    "Length": (len(Headers) / 1000),
                }
                Utilities.autoPrint(
                    text=f"Sending Alert:\n{EASData.EASText}\n{ALRT}",
                    classType="GENERATOR",
                    severity=severity.info,
                )
                if self.logger and self.export:
                    self.log = Utilities.log(
                        self.callsign,
                        self.webhooks,
                        "Local Alert Originated",
                        ALRT,
                        "",
                        "",
                        True,
                        alertName,
                        "",
                        self.version,
                        notification=EndecManager.notification,
                        email=EndecManager.email,
                    )
                elif self.logger:
                    self.log = Utilities.log(
                        self.callsign,
                        self.webhooks,
                        "Local Alert Originated",
                        ALRT,
                        "",
                        "",
                        False,
                        "",
                        "",
                        self.version,
                        notification=EndecManager.notification,
                        email=EndecManager.email,
                    )
                EndecMon.AlertToOld(noCall, AlertData)
                CurrentAlert.append(
                    {
                        "Audio": Headers,
                        "Event": " ".join(EASData.evntText.split(" ")[1:]),
                        "Callsign": EASData.callsign,
                        "Type": "Alert",
                        "Protocol": ALRT,
                    }
                )
            elif ap == "4":
                if self.lastAlert["Audio"] == AudioSegment.empty():
                    Utilities.autoPrint(
                        text="No Alert Received to Relay. Ignoring.",
                        classType="GENERATOR",
                        severity=severity.info,
                    )
                    Utilities.autoPrint("================")
                    return True
                else:
                    Utilities.autoPrint(
                        text="Sending Last Alert...",
                        classType="GENERATOR",
                        severity=severity.info,
                    )
                    CurrentAlert.append(self.lastAlert)
            elif ap == "3":
                Utilities.autoPrint(
                    text="Creating Alert...",
                    classType="GENERATOR",
                    severity=severity.info,
                )
                EEE = Utilities.user_input(30, "AlertGen", "Enter Event Code")
                if EEE == None:
                    Utilities.autoPrint(
                        text="Menu Timeout.",
                        classType="GENERATOR",
                        severity=severity.info,
                    )
                    Utilities.autoPrint("================")
                    return False
                if len(EEE) != 3:
                    Utilities.autoPrint(
                        text="Invalid Event.",
                        classType="GENERATOR",
                        severity=severity.info,
                    )
                    Utilities.autoPrint("================")
                    return True
                if EEE in ["EAN", "EAT"]:
                    Utilities.autoPrint(
                        text="Blocked Event.",
                        classType="GENERATOR",
                        severity=severity.info,
                    )
                    Utilities.autoPrint("================")
                    return True
                CCC = Utilities.user_input(
                    30, "AlertGen", "Enter FIPS Codes (Dash Seperated)"
                )
                if CCC == None:
                    Utilities.autoPrint(
                        text="Menu Timeout.",
                        classType="GENERATOR",
                        severity=severity.info,
                    )
                    Utilities.autoPrint("================")
                    return False
                elif len(CCC) > 6:
                    for C in CCC.split("-"):
                        if len(C) != 6:
                            Utilities.autoPrint(
                                text="Invalid FIPS.",
                                classType="GENERATOR",
                                severity=severity.info,
                            )
                            Utilities.autoPrint("================")
                            return True
                elif len(CCC) < 6:
                    Utilities.autoPrint(
                        text="Invalid FIPS.",
                        classType="GENERATOR",
                        severity=severity.info,
                    )
                    Utilities.autoPrint("================")
                    return True
                TTT = Utilities.user_input(
                    30, "AlertGen", "Enter Expiration Time"
                )
                if TTT == None:
                    Utilities.autoPrint(
                        text="Menu Timeout.",
                        classType="GENERATOR",
                        severity=severity.info,
                    )
                    Utilities.autoPrint("================")
                    return False
                elif len(TTT) != 4:
                    Utilities.autoPrint(
                        text="Invalid Expiration.",
                        classType="GENERATOR",
                        severity=severity.info,
                    )
                    Utilities.autoPrint("================")
                    return True
                elif not Utilities.isInt(TTT):
                    Utilities.autoPrint(
                        text="Invalid Expiration.",
                        classType="GENERATOR",
                        severity=severity.info,
                    )
                    Utilities.autoPrint("================")
                    return True
                Utilities.autoPrint(
                    text=f"Generating {EEE}...",
                    classType="GENERATOR",
                    severity=severity.info,
                )
                noCall = f"ZCZC-EAS-{EEE}-{CCC}+{TTT}-{DT.utcnow().strftime('%j%H%M')}-"
                # with open('alertCall.txt', 'r') as f:
                #     alertCallSign = f.read().replace('[', '').replace(']', '')

                alertCallSign = EndecManager.config["Callsign"]
                if len(alertCallSign) == 1:
                    alertCallSign = alertCallSign+'       '
                elif len(alertCallSign) == 2:
                    alertCallSign = alertCallSign+'      '
                elif len(alertCallSign) == 3:
                    alertCallSign = alertCallSign+'     '
                elif len(alertCallSign) == 4:
                    alertCallSign = alertCallSign+'    '
                elif len(alertCallSign) == 5:
                    alertCallSign = alertCallSign+'   '
                elif len(alertCallSign) == 6:
                    alertCallSign = alertCallSign+'  '
                elif len(alertCallSign) == 7:
                    alertCallSign = alertCallSign+' '
                elif len(alertCallSign) == 8:
                    alertCallSign = alertCallSign
                else:
                    print('[RELAY] CALLSIGN TOO LONG! Setting to default.')
                    alertCallSign = 'EASDCODR'
                ALRT = f"{noCall}{alertCallSign}-"

                EASData = EAS2Text(ALRT)
                Headers = EASGen.genEAS(
                    header=ALRT,
                    attentionTone=False,
                    mode=self.config["Emulation"],
                ).set_frame_rate(self.samplerate)
                alertName = f"{self.exportFolder}/EAS_{EASData.org}-{EASData.evnt}-{EASData.timeStamp}-{EASData.callsign.replace('/', '-').strip().replace(' ', '-')}.wav"
                if self.export:
                    Headers.export(alertName)
                AlertData = {
                    "Monitor": "AlertGen",
                    "Time": mktime(DT.utcnow().timetuple()),
                    "Event": " ".join(EASData.evntText.split(" ")[1:]),
                    "Protocol": noCall,
                    "From": EASData.callsign,
                    "Filter": {
                        "Matched": True,
                        "Name": "AlertGen",
                        "Actions": "Relay:Now",
                    },
                    "Length": (len(Headers) / 1000),
                }
                Utilities.autoPrint(
                    text=f"Sending Alert:\n{EASData.EASText}\n{ALRT}",
                    classType="GENERATOR",
                    severity=severity.info,
                )
                if self.logger and self.export:
                    self.log = Utilities.log(
                        self.callsign,
                        self.webhooks,
                        "Local Alert Originated",
                        ALRT,
                        "",
                        "",
                        True,
                        alertName,
                        "",
                        self.version,
                        notification=EndecManager.notification,
                        email=EndecManager.email,
                    )
                elif self.logger:
                    self.log = Utilities.log(
                        self.callsign,
                        self.webhooks,
                        "Local Alert Originated",
                        ALRT,
                        "",
                        "",
                        False,
                        "",
                        "",
                        self.version,
                        notification=EndecManager.notification,
                        email=EndecManager.email,
                    )
                EndecMon.AlertToOld(noCall, AlertData)
                CurrentAlert.append(
                    {
                        "Audio": Headers,
                        "Event": " ".join(EASData.evntText.split(" ")[1:]),
                        "Callsign": EASData.callsign,
                        "Type": "Alert",
                        "Protocol": ALRT,
                    }
                )
            elif ap == "5":
                Utilities.autoPrint(
                    text="Aborting Alert Gen.",
                    classType="GENERATOR",
                    severity=severity.info,
                )
                Utilities.autoPrint("================")
                return True
            else:
                Utilities.autoPrint(
                    text="Invalid Command.",
                    classType="GENERATOR",
                    severity=severity.info,
                )
                Utilities.autoPrint("================")
                return True
            Utilities.autoPrint("================")
            return False

    def ConfigMenu(self):
        Utilities.autoPrint("=== ConfigManager ===")
        while True:
            Utilities.autoPrint(
                f"1) Change Speaker State (Currently {'Enabled' if self.speaker else 'Disabled'})\n2) Callsign\n3) Filters\n4) Logger Config\n5) Playout Managers\n6) Local FIPS\n7) Monitors\n8) Reload Config\n9) Return"
            )
            cp = Utilities.user_input(30, cmdName="ConfigManager")
            if cp == None:
                Utilities.autoPrint(
                    text="Menu Timeout.",
                    classType="CONFIG",
                    severity=severity.info,
                )
                Utilities.autoPrint("=====================")
                return False
            elif cp == "1":
                if self.speaker == False:
                    Utilities.autoPrint(
                        text="Creating Playout (Audio)",
                        classType="PLAYOUT",
                        severity=severity.info,
                    )
                    self.player = PyAudio().open(
                        format=paInt16,
                        channels=self.channels,
                        rate=self.samplerate,
                        output=True,
                    )  # Will scream in pain
                    self.speaker = True
                    Utilities.autoPrint(
                        text=f"Speaker Enabled.",
                        classType="CONFIG",
                        severity=severity.info,
                    )
                    self.config["Speaker"] = self.speaker
                    with open(configFile, "w") as f:
                        dump(self.config, f, indent=4)
                    Utilities.autoPrint("=====================")
                    return True
                elif self.speaker == True:
                    if not self.Playout:
                        if self.AlertAvailable:
                            Utilities.autoPrint(
                                text="Waiting for Alert to end...",
                                classType="CONFIG",
                                severity=severity.info,
                            )
                            while self.AlertAvailable:
                                sleep(0.25)
                        self.player.close()
                        self.player = None
                    self.speaker = False
                    Utilities.autoPrint(
                        text=f"Speaker Disabled.",
                        classType="CONFIG",
                        severity=severity.info,
                    )
                    self.config["Speaker"] = self.speaker
                    with open(configFile, "w") as f:
                        dump(self.config, f, indent=4)
                    Utilities.autoPrint("=====================")
                    return True
            elif cp == "2":
                Utilities.autoPrint(
                    text=f'Current Callsign is "{self.callsign}".',
                    classType="CONFIG",
                    severity=severity.info,
                )
                Utilities.autoPrint("1) Change Callsign\n2) Return")
                cp2 = Utilities.user_input(30, cmdName="ConfigManager")
                if cp2 == None:
                    Utilities.autoPrint(
                        text="Menu Timeout.",
                        classType="CONFIG",
                        severity=severity.info,
                    )
                    Utilities.autoPrint("=====================")
                    return False
                elif cp2 == "1":
                    call = Utilities.user_input(
                        30, cmdName="ConfigManager", cmdText="Enter a Callsign"
                    )
                    if call == None:
                        Utilities.autoPrint(
                            text="Menu Timeout.",
                            classType="CONFIG",
                            severity=severity.info,
                        )
                        Utilities.autoPrint("=====================")
                        return False
                    else:
                        if len(call) <= 8:
                            self.setCallsign(call.ljust(8, " "))
                        else:
                            Utilities.autoPrint(
                                text="Callsign too long. Trimming...",
                                classType="CONFIG",
                                severity=severity.info,
                            )
                            self.setCallsign(call[:8])
                        Utilities.autoPrint(
                            text=f'New Callsign Set: "{self.callsign}"',
                            classType="CONFIG",
                            severity=severity.info,
                        )
                        self.config["Callsign"] = self.callsign
                        with open(configFile, "w") as f:
                            dump(self.config, f, indent=4)
                        Utilities.autoPrint("=====================")
                        return True
                elif cp2 == "2":
                    Utilities.autoPrint("=====================")
                    return True
                else:
                    Utilities.autoPrint(
                        text="Invalid Menu Option.",
                        classType="CONFIG",
                        severity=severity.info,
                    )
                    Utilities.autoPrint("=====================")
                    return False
            elif cp == "3":
                Utilities.autoPrint(
                    text="Not implemented yet!",
                    classType="CONFIG",
                    severity=severity.info,
                )
                Utilities.autoPrint("=====================")
                return True
            elif cp == "4":
                whString = "\n".join(self.webhooks)
                Utilities.autoPrint(
                    text=f"Current Logger Config:\nEnabled: {self.logger}\nWebhooks:\n{whString}",
                    classType="CONFIG",
                    severity=severity.info,
                )
                Utilities.autoPrint(
                    "1) Change Logger State\n2) Add webhook\n3) Remove webhook\n4) Return"
                )
                fipCmd = Utilities.user_input(30, cmdName="ConfigManager")
                if fipCmd == None:
                    Utilities.autoPrint(
                        text="Menu Timeout.",
                        classType="CONFIG",
                        severity=severity.info,
                    )
                    Utilities.autoPrint("=====================")
                    return False
                elif fipCmd == "1":
                    if self.logger == False:
                        Utilities.autoPrint(
                            text="Logger Enabled",
                            classType="CONFIG",
                            severity=severity.info,
                        )
                        self.logger = True
                        with open(configFile, "w") as f:
                            dump(self.config, f, indent=4)
                        Utilities.autoPrint("=====================")
                        return True
                    elif self.logger == True:
                        Utilities.autoPrint(
                            text="Logger Disabled",
                            classType="CONFIG",
                            severity=severity.info,
                        )
                        self.logger = False
                        with open(configFile, "w") as f:
                            dump(self.config, f, indent=4)
                        Utilities.autoPrint("=====================")
                        return True
                elif fipCmd == "2":
                    fipCmd2 = Utilities.user_input(
                        30,
                        cmdName="ConfigManager",
                        cmdText="Enter new Webhook",
                    )
                    if fipCmd2 == None:
                        Utilities.autoPrint(
                            text="Menu Timeout.",
                            classType="CONFIG",
                            severity=severity.info,
                        )
                        Utilities.autoPrint("=====================")
                        return False
                    elif fipCmd2 not in self.webhooks:
                        self.webhooks.append(fipCmd2)
                        with open(configFile, "w") as f:
                            dump(self.config, f, indent=4)
                        Utilities.autoPrint(
                            text=f"Webhook Added.",
                            classType="CONFIG",
                            severity=severity.info,
                        )
                        Utilities.autoPrint("=====================")
                        return True
                    else:
                        Utilities.autoPrint(
                            text=f"Webhook Already in list.",
                            classType="CONFIG",
                            severity=severity.info,
                        )
                        Utilities.autoPrint("=====================")
                        return True
                elif fipCmd == "3":
                    fipCmd2 = Utilities.user_input(
                        30,
                        cmdName="ConfigManager",
                        cmdText="Enter Webhook to Remove",
                    )
                    if fipCmd2 == None:
                        Utilities.autoPrint(
                            text="Menu Timeout.",
                            classType="CONFIG",
                            severity=severity.info,
                        )
                        Utilities.autoPrint("=====================")
                        return False
                    elif fipCmd2 in self.webhooks:
                        self.webhooks.remove(fipCmd2)
                        with open(configFile, "w") as f:
                            dump(self.config, f, indent=4)
                        Utilities.autoPrint(
                            text=f"Webhook Removed.",
                            classType="CONFIG",
                            severity=severity.info,
                        )
                        Utilities.autoPrint("=====================")
                        return True
                    else:
                        Utilities.autoPrint(
                            text=f"Webhook Not in list.",
                            classType="CONFIG",
                            severity=severity.info,
                        )
                        Utilities.autoPrint("=====================")
                        return True
                elif fipCmd == "4":
                    Utilities.autoPrint("=====================")
                    return True
                else:
                    Utilities.autoPrint(
                        text="Invalid Menu Option.",
                        classType="CONFIG",
                        severity=severity.info,
                    )
                    Utilities.autoPrint("=====================")
                    return False
            elif cp == "5":
                Utilities.autoPrint(
                    text="Not implemented yet!",
                    classType="CONFIG",
                    severity=severity.info,
                )
                Utilities.autoPrint("=====================")
                return True
            elif cp == "6":
                Utilities.autoPrint(
                    text=f"Current Local FIPS:\n{', '.join(self.localFIPS)}",
                    classType="CONFIG",
                    severity=severity.info,
                )
                Utilities.autoPrint(
                    "1) Remove FIPS code\n2) Add FIPS code\n3) Return"
                )
                fipCmd = Utilities.user_input(30, cmdName="ConfigManager")
                if fipCmd == None:
                    Utilities.autoPrint(
                        text="Menu Timeout.",
                        classType="CONFIG",
                        severity=severity.info,
                    )
                    Utilities.autoPrint("=====================")
                    return False
                elif fipCmd == "1":
                    fipCmd2 = Utilities.user_input(
                        30,
                        cmdName="ConfigManager",
                        cmdText="Enter FIPS code to Remove",
                    )
                    if fipCmd2 in self.localFIPS:
                        self.localFIPS.remove(fipCmd2)
                        self.config["LocalFIPS"] = self.localFIPS
                        with open(configFile, "w") as f:
                            dump(self.config, f, indent=4)
                        Utilities.autoPrint(
                            text=f"FIPS Code Removed.",
                            classType="CONFIG",
                            severity=severity.info,
                        )
                        Utilities.autoPrint("=====================")
                        return True
                    elif fipCmd2 == None:
                        Utilities.autoPrint(
                            text="Menu Timeout.",
                            classType="CONFIG",
                            severity=severity.info,
                        )
                        Utilities.autoPrint("=====================")
                        return False
                    else:
                        Utilities.autoPrint(
                            text=f"FIPS Code not in List.",
                            classType="CONFIG",
                            severity=severity.info,
                        )
                        Utilities.autoPrint("=====================")
                        return True
                elif fipCmd == "2":
                    fipCmd2 = Utilities.user_input(
                        30,
                        cmdName="ConfigManager",
                        cmdText="Enter FIPS code to Add",
                    )
                    if fipCmd2 not in self.localFIPS:
                        self.localFIPS.append(fipCmd2)
                        self.config["LocalFIPS"] = self.localFIPS
                        with open(configFile, "w") as f:
                            dump(self.config, f, indent=4)
                        Utilities.autoPrint(
                            text=f"FIPS Code Added.",
                            classType="CONFIG",
                            severity=severity.info,
                        )
                        Utilities.autoPrint("=====================")
                        return True
                    elif fipCmd2 == None:
                        Utilities.autoPrint(
                            text="Menu Timeout.",
                            classType="CONFIG",
                            severity=severity.info,
                        )
                        Utilities.autoPrint("=====================")
                        return False
                    else:
                        Utilities.autoPrint(
                            text=f"FIPS Code Already in list.",
                            classType="CONFIG",
                            severity=severity.info,
                        )
                        Utilities.autoPrint("=====================")
                        return True
                elif fipCmd == "3":
                    Utilities.autoPrint("=====================")
                    return True
                else:
                    Utilities.autoPrint(
                        text="Invalid Menu Option.",
                        classType="CONFIG",
                        severity=severity.info,
                    )
                    Utilities.autoPrint("=====================")
                    return False
            elif cp == "7":
                mons = []
                for monitor in self.monitors:
                    mons.append(f'{monitor.monitor["URL"]}')
                monText = "\n".join(mons)
                Utilities.autoPrint(
                    text=f"Current Monitors:\n{monText}",
                    classType="CONFIG",
                    severity=severity.info,
                )
                Utilities.autoPrint(
                    "1) Remove Monitor\n2) Add Monitor\n3) Return"
                )
                fipCmd = Utilities.user_input(30, cmdName="ConfigManager")
                if fipCmd == None:
                    Utilities.autoPrint(
                        text="Menu Timeout.",
                        classType="CONFIG",
                        severity=severity.info,
                    )
                    Utilities.autoPrint("=====================")
                    return False
                elif fipCmd == "1":
                    fipCmd2 = Utilities.user_input(
                        30,
                        cmdName="ConfigManager",
                        cmdText="Enter Monitor to Remove",
                    )
                    if fipCmd2 in ['AUD", "SDR']:
                        Utilities.autoPrint(
                            text=f"Special Monitor Removal not supported yet.",
                            classType="CONFIG",
                            severity=severity.info,
                        )
                        Utilities.autoPrint("=====================")
                        return True
                    elif fipCmd2 in mons:
                        mons.remove(fipCmd2)
                        self.config["Monitors"] = mons
                        with open(configFile, "w") as f:
                            dump(self.config, f, indent=4)
                        for monitor in self.monitors:
                            if fipCmd2 == monitor.monitor["URL"]:
                                monitor.killMon()
                                self.monitors.remove(monitor)
                        Utilities.autoPrint(
                            text=f"Monitor Removed.",
                            classType="CONFIG",
                            severity=severity.info,
                        )
                        Utilities.autoPrint("=====================")
                        return True
                    elif fipCmd2 == None:
                        Utilities.autoPrint(
                            text="Menu Timeout.",
                            classType="CONFIG",
                            severity=severity.info,
                        )
                        Utilities.autoPrint("=====================")
                        return False
                    else:
                        Utilities.autoPrint(
                            text=f"Monitor not in List.",
                            classType="CONFIG",
                            severity=severity.info,
                        )
                        Utilities.autoPrint("=====================")
                        return True
                elif fipCmd == "2":
                    fipCmd2 = Utilities.user_input(
                        30,
                        cmdName="ConfigManager",
                        cmdText="Enter Montior to Add",
                    )
                    if fipCmd2 not in mons:
                        mons.append(fipCmd2)
                        self.config["Monitors"] = mons
                        with open(configFile, "w") as f:
                            dump(self.config, f, indent=4)
                        self.monitors.append(EndecMon(fipCmd2))
                        Utilities.autoPrint(
                            text=f"Monitor Added.",
                            classType="CONFIG",
                            severity=severity.info,
                        )
                        Utilities.autoPrint("=====================")
                        return True
                    elif fipCmd2 == None:
                        Utilities.autoPrint(
                            text="Menu Timeout.",
                            classType="CONFIG",
                            severity=severity.info,
                        )
                        Utilities.autoPrint("=====================")
                        return False
                    else:
                        Utilities.autoPrint(
                            text=f"Monitor Already in list.",
                            classType="CONFIG",
                            severity=severity.info,
                        )
                        Utilities.autoPrint("=====================")
                        return True
                elif fipCmd == "3":
                    Utilities.autoPrint("=====================")
                    return True
                else:
                    Utilities.autoPrint(
                        text="Invalid Menu Option.",
                        classType="CONFIG",
                        severity=severity.info,
                    )
                    Utilities.autoPrint("=====================")
                    return False
            elif cp == "8":
                Utilities.autoPrint(
                    text="Not Implemented yet!",
                    classType="CONFIG",
                    severity=severity.info,
                )
                Utilities.autoPrint("=====================")
                return True
            elif cp == "9":
                Utilities.autoPrint("=====================")
                return True
            else:
                Utilities.autoPrint(
                    text="Invalid Menu Option.",
                    classType="CONFIG",
                    severity=severity.info,
                )
                Utilities.autoPrint("=====================")
                return False

    def UserMenu(self):
        Utilities.autoPrint("=== Menu ===")
        while True:
            if not self.playback:
                Utilities.autoPrint(
                    "1) Encoder\n2) ENDEC Config\n3) Print Alert Logs\n4) ENDEC Stats\n5) Reboot\n6) Shutdown\n7) Close Menu"
                )
            else:
                Utilities.autoPrint(
                    "1) Abort Playback\n2) ENDEC Config\n3) Print Alert Logs\n4) ENDEC Stats\n5) Reboot\n6) Shutdown\n7) Close Menu"
                )
            ip = Utilities.user_input(30)
            if ip == None:
                Utilities.autoPrint(
                    text="Menu Timeout.",
                    classType="ENDEC",
                    severity=severity.info,
                )
                Utilities.autoPrint("============")
                break
            else:
                if ip == "1" and not self.playback:
                    ret = self.IssueAlert()
                    if ret == True:
                        pass
                    else:
                        Utilities.autoPrint("============")
                        break
                elif ip == "1" and self.playback:
                    Utilities.autoPrint(
                        text="Aborting Playback...",
                        classType="ENDEC",
                        severity=severity.info,
                    )
                    self.playback = False
                    Utilities.autoPrint("============")
                    break
                elif ip == "2":
                    ret = self.ConfigMenu()
                    if ret:
                        pass
                    else:
                        Utilities.autoPrint("============")
                        break
                elif ip == "3":
                    Utilities.autoPrint("============")
                    Utilities.autoPrint(
                        text="\nSent Alerts:",
                        classType="ENDEC",
                        severity=severity.info,
                    )
                    if EndecMon.receivedAlerts == {}:
                        Utilities.autoPrint(
                            text="No alerts relayed.",
                            classType="ENDEC",
                            severity=severity.info,
                        )
                    else:
                        for i in EndecMon.receivedAlertsIndex:
                            Utilities.autoPrint(
                                "======================================="
                            )
                            Utilities.autoPrint(
                                text=f"{DT.fromtimestamp(EndecMon.receivedAlerts[i]['Time']).strftime('%m/%d/%y, %H:%M')} UTC:\n    {EndecMon.receivedAlerts[i]['Event']} from {EndecMon.receivedAlerts[i]['From']} via {EndecMon.receivedAlerts[i]['Monitor']}\n    Protocol: {EndecMon.receivedAlerts[i]['Protocol']}{EndecMon.receivedAlerts[i]['From']}-\n    Filter: {EndecMon.receivedAlerts[i]['Filter']['Name']} > {EndecMon.receivedAlerts[i]['Filter']['Actions']}\n    Length: {EndecMon.receivedAlerts[i]['Length']} Seconds",
                                classType="ENDEC",
                                severity=severity.info,
                            )
                        Utilities.autoPrint(
                            "=======================================\n"
                        )
                    break
                elif ip == "4":
                    Utilities.autoPrint("============")
                    Utilities.autoPrint(
                        text="\nCurrent ENDEC State:\n=======================================",
                        classType="ENDEC",
                        severity=severity.info,
                    )
                    Utilities.autoPrint(
                        f"  PLAYBACK: {self.playback}\n    PLAYER: {self.Playout}\n   ICECAST: {self.IcecastPlayout}\n  OVERRIDE: {self.OverrideManager.is_alive()}\n   AUTO-DJ: {self.DJ.is_alive()}\nALRT AVAIL: {self.AlertAvailable}\nNOW PLAYNG: {self.nowPlaying}\nALRT QUEUE: {len(CurrentAlert)}"
                    )
                    Utilities.autoPrint(
                        text="=======================================\n\nENDEC Alert Count (This session):\n=======================================",
                        classType="ENDEC",
                        severity=severity.info,
                    )
                    Utilities.autoPrint(
                        f"TOTAL MESG COUNT: {self.MessageCount}\nALERT MESG COUNT: {self.AlertCount}\n  CAP MESG COUNT: {self.CapCount}\n  OVERRIDE COUNT: {self.OverrideCount}"
                    )
                    Utilities.autoPrint(
                        "======================================="
                    )
                    Utilities.autoPrint(
                        text="\nCurrent Monitors:",
                        classType="ENDEC",
                        severity=severity.info,
                    )
                    for monitor in self.monitors:
                        Utilities.autoPrint(
                            f"=======================================\n[MANAGER] Monitor {monitor.monitorName}:\n     TYPE: {monitor.monitor['Type']}\n      URL: {monitor.monitor['URL']}\n    STATE: {monitor.MonState()}\n    ALERT: {monitor.monitor['Alert']}\nATTN TONE: {monitor.monitor['AttentionTone']}"
                        )
                    Utilities.autoPrint(
                        "=======================================\n"
                    )
                    break
                elif ip == "5":
                    if self.playback:
                        Utilities.autoPrint(
                            text="Waiting for Playback to end...",
                            classType="ENDEC",
                            severity=severity.info,
                        )
                        self.CurrentAlert = []
                        self.killMonitors()
                        while self.playback:
                            sleep(1)
                    Utilities.autoPrint(
                        text="Restarting ENDEC...",
                        classType="ENDEC",
                        severity=severity.info,
                    )
                    self.CurrentAlert = []
                    self.KillEndec()
                    return False
                elif ip == "6":
                    if self.playback:
                        Utilities.autoPrint(
                            text="Waiting for Playback to end...",
                            classType="ENDEC",
                            severity=severity.info,
                        )
                        self.killMonitors()
                        self.CurrentAlert = []
                        while self.playback:
                            sleep(1)
                    Utilities.autoPrint(
                        text="Killing ENDEC...",
                        classType="ENDEC",
                        severity=severity.info,
                    )
                    self.CurrentAlert = []
                    self.KillEndec()
                    return None
                elif ip == "7":
                    Utilities.autoPrint("============")
                    break
                else:
                    Utilities.autoPrint(
                        text="Invalid Command.",
                        classType="ENDEC",
                        severity=severity.info,
                    )
                    Utilities.autoPrint("============")
                    break
        return True


def main(configFile):
    Utilities.autoPrint("Begin BOOT Sequence...")
    try:
        Endec = EndecManager(configFile=configFile)
        Utilities.autoPrint(
            f"Station {EndecManager.callsign.strip()} Started."
        )
        print(
            "====================================\nPress <ENTER> to enter the ENDEC Menu.\n"
        )
        while True:
            input()
            test69420 = Endec.UserMenu()
            if test69420 == None:
                exit(0)
            elif test69420 == False:
                return
    except KeyboardInterrupt:
        EndecManager.KillEndec()
        exit(0)


if __name__ == "__main__":
    try:
        configFile = argv[1]
    except IndexError:
        configFile = ".config"
    try:
        while True:
            Utilities.CLS()
            print(
                f"ASMARA TECHNOLOGIES SOFTWARE ENDEC {EndecManager.version}\n===================================="
            )
            print(f"OS: {Utilities.getOS()}")
            print("*** STARTING UP ***")
            main(configFile)
            print("Restarting ENDEC...")
            sleep(5)
    except KeyboardInterrupt:
        EndecManager.KillEndec()
        exit(0)
