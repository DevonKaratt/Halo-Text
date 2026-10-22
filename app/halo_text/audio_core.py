"""Bounded, testable audio segmentation. Samples are mono float32 at 16 kHz."""
from collections import deque
import numpy as np

SAMPLE_RATE=16000

class SpeechSegmenter:
    def __init__(self,threshold=.006,max_seconds=7.0,silence_seconds=.25):
        self.threshold=threshold
        self.max_samples=int(max_seconds*SAMPLE_RATE)
        self.silence_samples=int(silence_seconds*SAMPLE_RATE)
        self.reset()

    def reset(self):
        self.preroll=deque(maxlen=3)
        self.parts=[]
        self.total=0
        self.voiced=0
        self.silence=0

    def feed(self,samples):
        if not len(samples):
            return None
        speech=float(np.sqrt(np.mean(samples*samples)))>=self.threshold
        if not self.parts:
            if not speech:
                self.preroll.append(samples)
                return None
            self.parts=list(self.preroll)
            self.total=sum(len(p) for p in self.parts)
            self.preroll.clear()
        self.parts.append(samples)
        self.total+=len(samples)
        if speech:
            self.voiced+=len(samples)
            self.silence=0
        else:
            self.silence+=len(samples)
        if self.total>=self.max_samples or self.silence>=self.silence_samples:
            result=np.concatenate(self.parts) if self.voiced>=int(.3*SAMPLE_RATE) else None
            self.reset()
            return result
        return None

def subtitle_is_current(recorded_at,now,max_age=12.0):
    return 0<=now-recorded_at<=max_age


def estimate_pitch(samples,sample_rate=SAMPLE_RATE):
    """Approximate voiced fundamental range; never a speaker identity embedding."""
    estimates=[]
    width=int(.04*sample_rate)
    for start in range(0,max(0,len(samples)-width+1),max(width,int(.08*sample_rate))):
        frame=samples[start:start+width].astype(np.float64)
        frame-=frame.mean()
        if np.sqrt(np.mean(frame*frame))<.008:continue
        frame*=np.hanning(len(frame))
        corr=np.correlate(frame,frame,mode="full")[len(frame)-1:]
        low,high=int(sample_rate/350),int(sample_rate/70)
        lag=low+int(np.argmax(corr[low:high]))
        if corr[0]>0 and corr[lag]/corr[0]>.3:estimates.append(sample_rate/lag)
    return float(np.median(estimates)) if len(estimates)>=3 else 0.0


class ApproximateVoiceLabels:
    """Group broad pitch ranges; these are not speaker identities."""
    def __init__(self):
        self.centers=[]

    def label(self,pitch_hz):
        if not 70 <= pitch_hz <= 350:
            return "Voice"
        for index,center in enumerate(self.centers):
            if abs(pitch_hz-center)/center <= .22:
                self.centers[index]=.8*center+.2*pitch_hz
                return f"Voice {index+1} (approx.)"
        if len(self.centers)<3:
            self.centers.append(pitch_hz)
            return f"Voice {len(self.centers)} (approx.)"
        nearest=min(range(len(self.centers)),key=lambda i:abs(pitch_hz-self.centers[i]))
        return f"Voice {nearest+1} (approx.)"
