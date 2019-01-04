import json
import datetime
import pytz


def handler(event, context):
    data = {
        'output': 'Hello World,Owlting is coming,add cloudtrail !!!',
        'timestamp': datetime.datetime.utcnow().replace(tzinfo=pytz.utc)(),
'new timestamp':datetime.now(pytz.utc)
    }
    return {'statusCode': 200,
            'body': json.dumps(data),
            'headers': {'Content-Type': 'application/json'}}
