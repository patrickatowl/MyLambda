import json
import datetime


def handler(event, context):
    data = {
        'output': 'Hello World,Owlting is coming,add cloudtrail !!!',
        'timestamp': datetime.datetime.utcnow().isoformat()
    }
    return {'statusCode': 200,
            'body': json.dumps(data),
            'headers': {'Content-Type': 'application/json'}}
