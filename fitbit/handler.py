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
from model import FitbitGoalsReported
from model import OAuthRequestToken

import util
from oauth2client.anyjson import simplejson
from apiclient.errors import HttpError

from fitbit.client import FitbitAPI

TO_MILES = 0.6213711

GOAL_TIMECARD = """
<article>
 <section style="margin-top:50px">
  <center>
  <p class="green">The daily goal reached!</p>
  <p style="margin-top:60px">
    <img src="https://m-distance.appspot.com/static/images/%s.png">&nbsp;<span style="vertical-align:25px" class="text-x-large">%s</span>
  </p>
  </center>
</section>
%s
</article>
"""

BATTERY_TIMECARD = """
<article>
 <section style="margin-top:50px">
  <center>
  <p class="red"><strong>Low battery level!</strong></p><p class="text-small">Recharge your Fitbit device soon.</p>
  <p style="margin-top:20px">
    <img src="https://m-distance.appspot.com/static/images/battery.png">
  </p>
  </center>
</section>
</article>
"""

TIMECARD_ROW = """
    <tr>
      <td><img src="https://m-distance.appspot.com/static/images/%s.png"></td>
      <td style="vertical-align:middle">
        <p>%s</p>
        <p>%s</p>
      </td>
      <td style="vertical-align:middle"><img src="https://m-distance.appspot.com/static/images/progress/progress%s.png" height="110"></td>
    </tr>
"""

TIMECARD_PAGE = """
<article>
  <section>
    <table>
    <tbody>
%s

%s
  </section>
%s  
</article>
"""

TIMECARD_COVER_FOOTER = '<footer><p>Tap to see more</p></footer>'

STATS_TIMECARD_FULL = "%s %s %s" % \
(TIMECARD_PAGE % (TIMECARD_ROW % ('steps', '%s', 'Steps', '%s'), TIMECARD_ROW % ('calories', '%s', 'Burned Calories', '%s'), TIMECARD_COVER_FOOTER), \
 TIMECARD_PAGE % (TIMECARD_ROW % ('active_minutes', '%s min', 'Very Active Mins', '%s'), TIMECARD_ROW % ('distance', '%s miles', 'Distance', '%s'), ''), \
 TIMECARD_PAGE % (TIMECARD_ROW % ('floors', '%s', 'Floors', '%s'), '', '')) 

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
      distance = float(info['summary']['distances'][0]['distance']) * TO_MILES #TODO: find 'total' in array
      caloriesOut = int(info['summary']['caloriesOut'])
      activeMinutes = int(info['summary']['veryActiveMinutes'])

      floors = 0
      if info['summary'].has_key('floors'):
        floors = int(info['summary']['floors'])

      if stats.steps != steps or stats.floors != floors or stats.distance != distance or stats.caloriesOut != caloriesOut or stats.activeMinutes != activeMinutes:
        stats.reported = False

      stats.steps = steps
      stats.floors = floors 
      stats.distance = distance 
      stats.caloriesOut = caloriesOut 
      stats.activeMinutes = activeMinutes

      stats.put()

      if info.has_key('goals'):
        _store_goals(userid, info)

      _check_if_reached_goal(userid, stats)
    
    except Exception as e:
      logging.error('Invalid message format (summary). Skipping. Error %s', str(e))
      logging.exception(e)
      return

#TODO: is one Job for all users enough?
class FitbitNotifyWorker(webapp2.RequestHandler):
  """Handler for Cron Job to send hourly updates to users.""" 

  def get(self):
    logging.debug('Cron job for Glass updates triggered')
    updates = FitbitStats.gql('WHERE reported = FALSE and steps > 0') 
    for u in updates:
      userid = u.key().name()
      logging.debug('Found update for user %s', userid)
      if util.get_preferences(userid).hourly_updates:
        _insert_stats_to_glass(userid, u, util.get_fitbit_goals(userid), True)
    
    users = OAuthRequestToken.all() 
    for u in users:
      userid = u.key().name()
      if util.get_preferences(userid).battery_level:
        _check_battery_level(userid)

class FitbitSampleWorker(webapp2.RequestHandler):
  """Handler for sample card requests.""" 

  @util.google_auth_required
  def post(self):
    logging.debug('Sample card requested')
    if not self.userid:
      logging.error('No Google User Id in the session')
      return

    stats = FitbitStats()
    goals = FitbitGoals()
    stats.steps = random.randrange(0, goals.steps)
    stats.distance = float(random.randrange(0, round(goals.distance))) + random.randrange(0, 100)/100 
    stats.caloriesOut = random.randrange(0, goals.caloriesOut)
    stats.activeMinutes = random.randrange(0, goals.activeMinutes)
    stats.floors = random.randrange(0, goals.floors)

    _insert_stats_to_glass(self.userid, stats, goals, False)

    _check_battery_level(self.userid)

    self.redirect('/')    

def _store_goals(userid, info):
  goals = util.get_fitbit_goals(userid)
  if not goals:
    goals = FitbitGoals(key_name=userid)

  try:
    goals.steps = int(info['goals']['steps'])
    goals.distance = float(info['goals']['distance']) * TO_MILES
    goals.caloriesOut = int(info['goals']['caloriesOut'])
    goals.activeMinutes = int(info['goals']['activeMinutes'])
    if info['goals'].has_key('floors'):
      goals.floors = int(info['goals']['floors'])
    else:
      goals.floors = 0

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

def _check_if_reached_goal(userid, stats):
  prefs = util.get_preferences(userid)
  if not prefs.goal_updates:
    return

  goals = util.get_fitbit_goals(userid)
  if not goals:
    goals = _fetch_goals(userid)
    if not goals:
      logging.warning('Sorry, cannot get goals. next time, maybe. User: %s', userid)
      return

  goals_reported = util.get_fitbit_goals_reported(userid)
  if not goals_reported:
    goals_reported = FitbitGoalsReported(key_name=userid)

  html = ''
  pages = 0
  #TODO: too much duplication. need to do some Python magic here  
  # Steps goal reached
  if goals_reported.steps:
    if stats.steps < goals.steps:
      goals_reported.steps = False
  else:    
    if stats.steps >= goals.steps:
      html += (GOAL_TIMECARD % ('steps', 'Steps', '%s'))
      pages += 1
      goals_reported.steps = True
      logging.debug('Goal for STEPS reached for user %s', userid)
    
  # CaloriesOut goal reached
  if goals_reported.caloriesOut:
    if stats.caloriesOut < goals.caloriesOut:
      goals_reported.caloriesOut = False
  else:    
    if stats.caloriesOut >= goals.caloriesOut:
      html += (GOAL_TIMECARD % ('calories', 'Burned Calories', '%s'))
      pages += 1
      goals_reported.caloriesOut = True
      logging.debug('Goal for CALORIES reached for user %s', userid)
    
  # activeMinutes goal reached
  if goals_reported.activeMinutes:
    if stats.activeMinutes < goals.activeMinutes:
      goals_reported.activeMinutes = False
  else:    
    if stats.activeMinutes >= goals.activeMinutes:
      html += (GOAL_TIMECARD % ('active_minutes', 'Very Active Minutes', '%s'))
      pages += 1
      goals_reported.activeMinutes = True
      logging.debug('Goal for ACTIVE MINUTES reached for user %s', userid)
    
  # Distance goal reached
  if goals_reported.distance:
    if stats.distance < goals.distance:
      goals_reported.distance = False
  else:    
    if stats.distance >= goals.distance:
      html += (GOAL_TIMECARD % ('distance', 'Distance', '%s'))
      pages += 1
      goals_reported.distance = True
      logging.debug('Goal for DISTANCE reached for user %s', userid)
    
  # floors goal reached
  if goals.floors > 0:
    if goals_reported.floors:
      if stats.floors < goals.floors:
        goals_reported.floors = False
    else:    
      if stats.floors >= goals.floors:
        html += (GOAL_TIMECARD % ('floors', 'Floors', '%s'))
        pages += 1
        goals_reported.floors = True
        logging.debug('Goal for FLOORS reached for user %s', userid)
  
  if html:
    if pages > 1:
      l = [TIMECARD_COVER_FOOTER]
    else:
      l = ['']

    for i in range(pages-1):
      l.append('')
    _insert_info_to_glass(userid, html % tuple(l))

  goals_reported.put()

def _insert_stats_to_glass(userid, stats, goals, store):
  logging.debug('Creating new stats timeline card for user %s.', userid)

  # locale.setlocale(locale.LC_ALL, 'en_US')
  s = locale.format("%d", stats.steps, grouping=True)
  percentage = int(round(stats.steps*100/goals.steps)) 

  body = {
    'notification': {'level': 'DEFAULT'},
    'html': STATS_TIMECARD_FULL % (stats.steps, _percentage(stats.steps, goals.steps), \
                             stats.caloriesOut, _percentage(stats.caloriesOut, goals.caloriesOut), \
                             stats.activeMinutes, _percentage(stats.activeMinutes, goals.activeMinutes), \
                             "%.2f" % stats.distance, _percentage(stats.distance, goals.distance), \
                             stats.floors, _percentage(stats.floors, goals.floors)
     ),
    'menuItems': [ { 'action': 'TOGGLE_PINNED' }, { 'action': 'DELETE' }]
  }
  credentials = util.credentials_by_userid(userid)
  try:
    mirror_service = util.create_google_service('mirror', 'v1', credentials)
    mirror_service.timeline().insert(body=body).execute()
    if store:
      stats.reported = True
      stats.put()
  except Exception as e:
    logging.warning('Cannot insert timecard for user %s. Error: %s', userid, str(e))
    logging.exception(e)

def _percentage(value, goal):
  if goal == 0:
    return 0
  p = int(round(value*100/goal)) 
  if p > 100:
    return 100
  return p 

def _insert_info_to_glass(userid, html):
  logging.debug('Creating new info timeline card for user %s.', userid)
  body = {
    'notification': {'level': 'DEFAULT'},
    'html': html,
    'menuItems': [ { 'action': 'DELETE' } ]
  }
  credentials = util.credentials_by_userid(userid)
  try:
    mirror_service = util.create_google_service('mirror', 'v1', credentials)
    mirror_service.timeline().insert(body=body).execute()
  except HttpError as he:
    logging.warning('Cannot insert timecard for user %s. Error: %s', userid, str(e))
    try:
      if he.resp.status == 401:
        _disable_user(userid)
    except: 
      pass
  except Exception as e:
    logging.warning('Cannot insert timecard for user %s. Error: %s', userid, str(e))
    logging.exception(e)

def _disable_user(userid):
  logging.info("Disabling user %s", userid)
  api = FitbitAPI(userid)
  if api.is_ready():
    api.clear_subscriptions()

def _check_battery_level(userid):
  api = FitbitAPI(userid)
  if not api.is_ready():
    return
  devices = api.get_devices_info()
  for d in devices:
    if d['type'] == 'TRACKER' and d['battery'] == 'Low':
      _insert_info_to_glass(userid, BATTERY_TIMECARD)


FITBIT_ROUTES = [
    ('/fitbit/subscription', FitbitSubscriptionHandler), # FitBit -> M-Distance. Callback for FitBit to notfy if there is an update 
    ('/fitbit/readupdates', FitbitUpdateWorker),         # M-Distance -> FitBit. Read Activity updates from Fitbit. Runs async when get notfication from FitBit
    ('/fitbit/notify', FitbitNotifyWorker),              # M-Distance -> Glass. Hourly job to send updates to Glass
    ('/fitbit/sample', FitbitSampleWorker)               # M-Distance -> Glass. Manually sends sample card to Glass 

]
