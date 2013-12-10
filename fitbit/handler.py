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

import locale

import logging
import webapp2

from google.appengine.api import urlfetch
from google.appengine.api import taskqueue

from model import Credentials
from model import Preferences
from model import FitbitStats
import util
from oauth2client.anyjson import simplejson

from fitbit.client import FitbitAPI

TIMECARD_TEMPLATE_HTML = """
<article>
  <figure>
    <img src="https://m-distance.appspot.com/static/images/fitbit-1024-blk-transparent.png" width="240">
  </figure>
  <section>
    <table class="text-small align-justify">       
      <tbody>
      <tr>
        <td>Steps</td><td>%s</td>
      </tr>
      <tr>
        <td>To Goal</td><td>%s%%</td>
      </tr>
      </tbody>
    </table>
  </section>
</article>
"""

class FitbitSubscriptionHandler(webapp2.RequestHandler):
  """Request Handler for the fitbit subscription endpoint.
     This handler is called by Fitbit
  """

  def post(self):
    logging.debug('SUBSCRIPTION UPDATE from Fitbit %s', self.request.body)
    content = self.request.POST.get('updates').file.read()
    taskqueue.add(url='/fitbit/readupdates', params={'data' : content})
    self.response.set_status(204)

class FitbitUpdateWorker(webapp2.RequestHandler):
  """Request Handler for Fitbit Update Worker.

     Reads latest updates from Fitbit and stores them in the Datastore
  """

  def post(self):
    data = self.request.get('data')
    updates = simplejson.loads(data)

    # last one is always most recent and we only care about most recent update
    update = updates[-1]
    userid = update['subscriptionId']
    api = FitbitAPI(userid)
    if not api.is_ready():
      logging.warning('No Fitbit login info for user %s', userid)
      return

    info = api.get_activities_info(update['date'])
    if not info:
      logging.error('Cannot read update for user %s', userid)
      return

    goal = int(info['goals']['steps'])
    steps = int(info['summary']['steps'])

    logging.debug('Got update for user %s STEPS: %s GOAL %s', userid, steps, goal)
    stats = util.get_fitbit_stats(userid)
    if not stats:
      stats = FitbitStats(key_name=userid)

    if stats.steps != steps:
      stats.reported = False

    stats.goal = goal
    stats.steps = steps
    stats.put()

    prefs = util.get_preferences(userid)
    if steps >= goal and prefs.goal_updates:     
      _insert_to_glass(userid, stats)

#TODO: is one Job for all users enough?
class FitbitNotifyWorker(webapp2.RequestHandler):
  """Handler for Cron Job to send hourly updates to users.""" 

  def get(self):
    logging.debug('Cron job triggered')
    #TODO: maybe we should keep FitBit stats and prefs in one table, so we can get this list in one query
    updates = FitbitStats.gql('WHERE reported = FALSE and steps > 0') 
    for u in updates:
      userid = u.key().name()
      logging.debug('Found update for user %s', userid)
      if util.get_preferences(userid).hourly_updates:
        _insert_to_glass(userid, u)

def _insert_to_glass(userid, stats):
  logging.debug('Creating new timeline card for user %s. Steps %s', userid, stats.steps)

  # locale.setlocale(locale.LC_ALL, 'en_US')
  s = locale.format("%d", stats.steps, grouping=True)
  percentage = int(round(stats.steps*100/stats.goal)) 

  body = {
    'notification': {'level': 'DEFAULT'},
    'html': TIMECARD_TEMPLATE_HTML % (s, percentage)
  }
  credentials = util.credentials_by_userid(userid)
  try:
    mirror_service = util.create_google_service('mirror', 'v1', credentials)
    mirror_service.timeline().insert(body=body).execute()
    stats.reported = True
    stats.put()
  except Exception as e:
    logging.warning('Cannot insert timecard for user %s. Error: %s', userid, str(e))


FITBIT_ROUTES = [
    ('/fitbit/subscription', FitbitSubscriptionHandler),
    ('/fitbit/readupdates', FitbitUpdateWorker),
    ('/fitbit/notify', FitbitNotifyWorker)
]
