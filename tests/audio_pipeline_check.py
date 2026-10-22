"""Generated speech only: local English ASR, Hindi translation and approved online TTS."""
from pathlib import Path
import sys,asyncio,json,io
from time import perf_counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from halo_text.paths import configure,ROOT
configure()
from halo_text.pipeline import preload_runtime
preload_runtime()
from halo_text.voice import available_voices,select_voice,synthesize
from halo_text.audio import SpeechEngine
from halo_text.config import Config
from halo_text.audio import decode_audio_file as decode_audio
folder=ROOT/'reports/audio';folder.mkdir(parents=True,exist_ok=True)
async def main():
 voices=await available_voices();engine=SpeechEngine(Config())
 rows=[]
 for i,(text,gender) in enumerate([('The train is late.','Male'),('Please close the door.','Female')]):
  source_voice=select_voice('en',voices,gender=gender)
  source_audio=await synthesize(text,source_voice,rate=0)
  (folder/f'generated_english_{i}.mp3').write_bytes(source_audio)
  samples=decode_audio(io.BytesIO(source_audio),sampling_rate=16000)
  start=perf_counter();result=engine.process(samples);processing=(perf_counter()-start)*1000
  if not result:raise RuntimeError('No generated speech recognized')
  target_voice=select_voice('hi',voices,gender=gender)
  start=perf_counter();output=await synthesize(result[1],target_voice);tts_ms=(perf_counter()-start)*1000
  (folder/f'generated_hindi_{i}.mp3').write_bytes(output)
  rows.append({'expected_english':text,'recognized_english':result[0],'translated':result[1],'input_seconds':len(samples)/16000,'recognition_translation_ms':round(processing,1),'tts_full_audio_ms':round(tts_ms,1),'post_chunk_processing_ms':round(processing+tts_ms,1),'source_pitch_hz':round(engine.last_pitch_hz,1),'voice':target_voice})
 report={'scope':'Two generated English phrases, local tiny.en CPU ASR and local Hindi translation; approved Microsoft online TTS. Timings exclude phrase listening duration, endpoint silence detection, output-device opening and playback. Full TTS response measured, not time-to-first-byte. Not live human accuracy evaluation.','cases':rows,'available_voices':len(voices)}
 (folder/'pipeline.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=True,indent=2),flush=True)
asyncio.run(main())
