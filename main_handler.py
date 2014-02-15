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

"""Request Handler for /main endpoint."""

__author__ = 'bird@codeminders.com (Alexander Sova)'

import io
import jinja2
import logging
import os
import webapp2

from google.appengine.api import memcache
from google.appengine.api import urlfetch

import httplib2
from apiclient import errors
from apiclient.http import MediaIoBaseUpload
from apiclient.http import BatchHttpRequest
from oauth2client.appengine import StorageByKeyName

from model import Credentials
from model import OAuthRequestToken

import util

from fitbit.client import FitbitAPI

jinja_environment = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))

class MainHandler(webapp2.RequestHandler):
  """Request Handler for the main endpoint."""

  def _render_template(self, message=None):
    """Render the main page template."""
    template_values = {'userId': self.userid}
    if message:
      template_values['message'] = message

    logging.debug("User ID: %s" % self.userid)

    api = FitbitAPI(self.userid)
    if api.is_ready():
      fitbit_user_profile = api.get_user_profile()
      if fitbit_user_profile:
        template_values['has_fitbit_device'] = True
        template_values['fitbit_avatar'] = fitbit_user_profile['user']['avatar']
        template_values['fitbit_name']   = fitbit_user_profile['user']['displayName']

        # check if subscription is still there
        subs = api.get_subscriptions()
        if len(subs) == 0:
          logging.debug('No subscription for user %s', self.userid)
          api.create_subscription()
        else:
          logging.debug('Found subscription for user %s', self.userid)
      else:
        self._remove_fitbit_device()

    prefs = util.get_preferences(self.userid)
    template_values['prefs_hourly_updates'] = prefs.hourly_updates
    template_values['prefs_goal_updates'] = prefs.goal_updates

    template = jinja_environment.get_template('templates/index.html')
    self.response.out.write(template.render(template_values))

  @util.google_auth_required
  def get(self):
    """Render the main page."""
    # Get the flash message and delete it.
    message = memcache.get(key=self.userid)
    memcache.delete(key=self.userid)
    self._render_template(message)

  @util.google_auth_required
  def post(self):
    """Execute the request and render the template."""
    operation = self.request.get('operation')
    # Dict of operations to easily map keys to methods.
    operations = {
        'addFitbitDevice': self._add_fitbit_device,
        'removeFitbitDevice': self._remove_fitbit_device,
        'savePreferences': self._save_preferences
    }
    if operation in operations:
      message = operations[operation]()
    else:
      message = "I don't know how to " + operation
    # Store the flash message for 5 seconds.
    memcache.set(key=self.userid, value=message, time=5)
    self.redirect('/')

  #TODO: should we use @util.fitbit_auth_required here?
  def _add_fitbit_device(self):
    """Add Fitbit device (OAuth flow initiated)."""

    api = FitbitAPI(self.userid)
    if not api.is_ready():
      self.redirect('/fitbitauth', abort=True)
      return  ''

  def _remove_fitbit_device(self):
    """Delete Fitbit device."""

    try:
      api = FitbitAPI(self.userid)
      if api.is_ready():
        api.delete_subscription(self.userid)
    except:
      logging.warn('Cannot delete subscription for user %s', userid)

    token_entity = OAuthRequestToken.get_by_key_name(self.userid)
    if token_entity:
        token_entity.delete()

  def _save_preferences(self):
    """Save user preferences."""
    prefs = util.get_preferences(self.userid)
    data = self.request.get_all('updates')
    prefs.hourly_updates = ('hourly' in data)
    prefs.goal_updates = ('goal' in data)
    prefs.put()


MAIN_ROUTES = [
    ('/', MainHandler)
]
