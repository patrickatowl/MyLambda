
import sys, io, subprocess, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

result = subprocess.run(
    ['gh', 'api', 'repos/owlting/owlnet_booking_api/branches/master/protection'],
    capture_output=True, text=True
)

if result.returncode != 0:
    print('Error:', result.stderr)
else:
    data = json.loads(result.stdout)
    print(json.dumps(data, indent=2, ensure_ascii=False))

