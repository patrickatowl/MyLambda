import json
import datetime
import pytz


def handler(event, context):
    data = {
        'output': 'Hello World,Owlting is coming,add cloudtrail !!!'

    }
    return {'statusCode': 200,
            'body': json.dumps(data),
            'headers': {'Content-Type': 'application/json'}}
