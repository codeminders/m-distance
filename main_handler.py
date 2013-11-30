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

__author__ = 'info@codeminders.com'

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
import util

#TODO: move to class
from fitbit.handler import create_subscription

jinja_environment = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))

class MainHandler(webapp2.RequestHandler):
  """Request Handler for the main endpoint."""

  def _render_template(self, message=None):
    """Render the main page template."""
    template_values = {'userId': self.userid}
    if message:
      template_values['message'] = message
    # self.mirror_service is initialized in util.google_auth_required.

    fitbit_service = util.create_fitbit_service(self)
    if not fitbit_service:
      self.redirect('/fitbitauth', abort=True)
      return
    
    r = fitbit_service.get('http://api.fitbit.com/1/user/-/profile.json', header_auth=True)
    fitbit_user_profile = r.json()
    template_values['fitbit_avatar'] = fitbit_user_profile['user']['avatar']
    template_values['fitbit_name']   = fitbit_user_profile['user']['displayName']

    template = jinja_environment.get_template('templates/index.html')
    self.response.out.write(template.render(template_values))

    #TODO: is this a right place?
    create_subscription(self)

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
        'insertItem': self._insert_item,
        'addFitbitDevice': self._add_fitbit_device
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

    fitbit_service = util.create_fitbit_service(self)
    if not fitbit_service:
      self.redirect('/fitbitauth', abort=True)
      return  ''


  def _insert_item(self):
    """Insert a timeline item."""
    logging.debug('Inserting timeline item')
    body = {
        'notification': {'level': 'DEFAULT'}
    }
    if self.request.get('html') == 'on':
      body['html'] = [self.request.get('message')]
    else:
      body['text'] = self.request.get('message')

    # self.mirror_service is initialized in util.google_auth_required.
    self.mirror_service.timeline().insert(body=body).execute()
    return  'A timeline item has been inserted.'

MAIN_ROUTES = [
    ('/', MainHandler)
]
