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
import random
import datetime

import logging
import webapp2

from google.appengine.api import urlfetch
from google.appengine.api import taskqueue

from model import Credentials
from model import Preferences
from model import FitbitStats
from model import FitbitGoals
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
      logging.error('No Fitbit login info for user %s', userid)
      return

    date = ''
    try:
      date = update['date']
      dt = datetime.datetime.today() - datetime.datetime.strptime(date, '%Y-%m-%d')
      if dt.days > 1:
        logging.warning('Historic update. Not interested. Skipping. Date: %s', date)
        return

    except Exception as e:
      logging.warning('Invalid message format (date). Skipping. Error: %s', str(e))
      return

    info = api.get_activities_info(date)
    if not info:
      logging.error('Cannot read update for user %s for date %s', userid, date)
      return

    try:

      stats = util.get_fitbit_stats(userid)
      if not stats:
        stats = FitbitStats(key_name=userid)

      steps  = int(info['summary']['steps'])
      floors = int(info['summary']['floors'])
      distance = float(info['summary']['distances'][0]['distance']) #TODO: find 'total' in array
      caloriesOut = int(info['summary']['caloriesOut'])
      activeMinutes = int(info['summary']['veryActiveMinutes'])
      if stats.steps != steps or stats.floors != floors or stats.distance != distance or stats.caloriesOut != caloriesOut or stats.activeMinutes != activeMinutes:
        stats.reported = False

      stats.steps = steps
      stats.floors = floors 
      stats.distance = distance 
      stats.caloriesOut = caloriesOut 
      stats.activeMinutes = activeMinutes

      stats.put()

      if info['goals']:
        _store_goals(userid, info)

      self.check_if_reached_goal(userid, stats)
    
    except Exception as e:
      logging.error('Invalid message format (summary). Skipping. Error %s', str(e))
      logging.exception(e)
      return

  def check_if_reached_goal(self, userid, stats):
    prefs = util.get_preferences(userid)
    if prefs.goal_updates:
      goals = util.get_fitbit_goals(userid)
      if not goals:
        goals = _fetch_goals(userid)
        if not goals:
          logging.warning('Sorry, cannot get goals. next time, maybe')
          return
    
      if stats.steps >= goals.steps or \
         stats.floors >= goals.floors or \
         stats.distance >= goals.distance or \
         stats.caloriesOut >= goals.caloriesOut or \
         stats.activeMinutes >= goals.activeMinutes:
        _insert_to_glass(userid, stats, util.get_fitbit_goals(userid))

#TODO: is one Job for all users enough?
class FitbitNotifyWorker(webapp2.RequestHandler):
  """Handler for Cron Job to send hourly updates to users.""" 

  def get(self):
    logging.debug('Cron job for Glass updates triggered')
    #TODO: maybe we should keep FitBit stats and prefs in one table, so we can get this list in one query
    updates = FitbitStats.gql('WHERE reported = FALSE and steps > 0') 
    for u in updates:
      userid = u.key().name()
      logging.debug('Found update for user %s', userid)
      if util.get_preferences(userid).hourly_updates:
        _insert_to_glass(userid, u, util.get_fitbit_goals(userid))

class FitbitSampleWorker(webapp2.RequestHandler):
  """Handler for sample card requests.""" 

  @util.google_auth_required
  def post(self):
    logging.debug('Sample card requested')
    if not self.userid:
      logging.error('No Google User Id in the session')
      return

    stats = FitbitStats()
    stats.steps = random.randrange(100,10000)
    golas = FitbitGoals()
    goals.steps = 10000
    _insert_to_glass(self.userid, stats)
    self.redirect('/')    

def _store_goals(userid, info):
  goals = util.get_fitbit_goals(userid)
  if not goals:
    goals = FitbitGoals(key_name=userid)

  try:
    goals.steps = int(info['goals']['steps'])
    goals.floors = int(info['goals']['floors'])
    goals.distance = float(info['goals']['distance'])
    goals.caloriesOut = int(info['goals']['caloriesOut'])
    goals.activeMinutes = int(info['goals']['activeMinutes'])

    goals.put()

    return goals
  except Exception as e:
    logging.warning('Cannot parse goals for user %s. Error: %s', userid, str(e))
    logging.exception(e)

#TODO: maybe to pass API object
def _fetch_goals(userid):
  logging.debug('Reading daily Activity goals for user %s' % userid)

  api = FitbitAPI(userid)
  if not api.is_ready():
    logging.error('No Fitbit login info for user %s', userid)
    return

  info = api.get_activities_goals()
  return _store_goals(userid, info)
  

def _insert_to_glass(userid, stats, goals):
  logging.debug('Creating new timeline card for user %s. Steps %s', userid, stats.steps)

  # locale.setlocale(locale.LC_ALL, 'en_US')
  s = locale.format("%d", stats.steps, grouping=True)
  percentage = int(round(stats.steps*100/goals.steps)) 

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
    ('/fitbit/subscription', FitbitSubscriptionHandler), # FitBit -> M-Distance. Callback for FitBit to notfy if there is an update 
    ('/fitbit/readupdates', FitbitUpdateWorker),         # M-Distance -> FitBit. Read Activity updates from Fitbit. Runs async when get notfication from FitBit
    ('/fitbit/notify', FitbitNotifyWorker),              # M-Distance -> Glass. Hourly job to send updates to Glass
    ('/fitbit/sample', FitbitSampleWorker)               # M-Distance -> Glass. Manually sends sample card to Glass 

]
