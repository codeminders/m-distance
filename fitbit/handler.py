# Copyright (C) 2013 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Request Handlers for /fitbit endpoints."""

__author__ = 'info@codeminders.com'


import logging
import webapp2

from google.appengine.api import urlfetch
from google.appengine.api import taskqueue

from model import Credentials
import util

from oauth2client.anyjson import simplejson

TIMECARD_TEMPLATE_HTML = """
<article>
  <figure>
    <img src="https://m-distance.appspot.com/static/images/fitbit-1024-blk-transparent.png" width="240">
  </figure>
  <section>
    Steps<br/><br/>%s
  </section>
</article>
"""

#TODO: move it somehwere
def create_subscription(handler):

  userid = util.load_session_credentials(handler)[0]
  logging.debug('Checking Fitbit subscription for user %s' % userid)

  # check if subscription exists
  fitbit_service = util.create_fitbit_service(handler)
  r = fitbit_service.get('http://api.fitbit.com/1/user/-/apiSubscriptions.json', header_auth=True)
  if r.status_code == 200:
    subs = r.json()['apiSubscriptions']

    exists = False
    for s in subs:
      if s['subscriptionId'] == userid:
        exists = True

    if not exists:
      r = fitbit_service.post('http://api.fitbit.com/1/user/-/apiSubscriptions/%s.json' % userid, data={}, header_auth=True)
      logging.info('Adding new subscription for user %s. The code: %s', userid, r.status_code)
      #TODO: retry if status code is not 201
    else:
      logging.debug('Found subscription for user %s', userid)
  
  else:
    logging.error('Cannot get list of Fitbit subscriptions for user %s', userid)


class FitbitSubscriptionHandler(webapp2.RequestHandler):
  """Request Handler for the fitbit subscription endpoint."""

  def post(self):
    logging.debug('POST: SUBSCRIPTION UPDATE from Fitbit %s', self.request.body)
    content = self.request.POST.get('updates').file.read()
    taskqueue.add(url='/fitbitupdate', params={'data' : content})
    self.response.set_status(204)

class FitbitSubscriptionWorker(webapp2.RequestHandler):
  """Request Handler for Fitbit Update Worker."""

  def post(self):
    data = self.request.get('data')
    logging.debug('SUBSCRIPTION UPDATE Worker: %s', data)
    updates = simplejson.loads(data)

    for update in updates:
      userid = update['subscriptionId']
      date = update['date']

      url = 'http://api.fitbit.com/1/user/-/activities/date/%s.json' % date
      fitbit_service = util.create_fitbit_service_for_user(userid)
      r = fitbit_service.get(url, header_auth=True)
      if r.status_code == 200:
        j = r.json()
        steps = j['summary']['steps']
        logging.debug('STEPS: %s', steps)    
        _insert_to_glass(userid, steps)
      else:
        logging.error('Cannot retrieve update from Fitbit. The code: %s', r.status_code)


def _insert_to_glass(userid, steps):
  logging.debug('Creating new timeline card for user %s. Steps %s', userid, steps)
  body = {
    'notification': {'level': 'DEFAULT'},
    #'text': 'Steps: %s' % steps
    'html': TIMECARD_TEMPLATE_HTML % steps
  }
  credentials = util.credentials_by_userid(userid)
  mirror_service = util.create_google_service('mirror', 'v1', credentials)
  mirror_service.timeline().insert(body=body).execute()


FITBIT_ROUTES = [
    ('/fitbitsub', FitbitSubscriptionHandler),
    ('/fitbitupdate', FitbitSubscriptionWorker)
]
