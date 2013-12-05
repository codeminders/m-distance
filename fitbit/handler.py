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

__author__ = 'bird@codeminders.com (Alexander Sova)'


import logging
import webapp2

from google.appengine.api import urlfetch
from google.appengine.api import taskqueue

from model import Credentials
import util

from oauth2client.anyjson import simplejson

from fitbit.client import FitbitAPI


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

    #TODO: find most recent one!
    for update in updates:
      userid = update['subscriptionId']
      api = FitbitAPI(userid)
      if not api.is_ready():
        logging.warning('No Fitbit login info for user %s', userid)
        return

      date = update['date']
      info = api.get_activities_info(date)
      goal = info['goals']['steps']
      steps = info['summary']['steps']

      logging.debug('STEPS: %s GOAL %s', steps, goal)    
      _insert_to_glass(userid, steps)

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
