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

"""Utility functions."""

__author__ = 'bird@codeminders.com (Alexander Sova)'


from urlparse import urlparse

from google.appengine.ext import db

import logging
import httplib2
from apiclient.discovery import build
from oauth2client.appengine import StorageByKeyName
from oauth2client.client import AccessTokenRefreshError
import sessions

from model import Credentials
from model import OAuthRequestToken
from model import Preferences
from model import FitbitStats
from model import FitbitGoals
from model import FitbitGoalsReported
from model import GlassTimelineItem

from rauth.service import OAuth1Service

from oauth2client.anyjson import simplejson

# Load the secret that is used for client side sessions
# Create one of these for yourself with, for example:
# python -c "import os; print os.urandom(64)" > session.secret
SESSION_SECRET = open('session.secret').read()

def get_full_url(request_handler, path):
  """Return the full url from the provided request handler and path."""
  pr = urlparse(request_handler.request.url)
  return '%s://%s%s' % (pr.scheme, pr.netloc, path)


def load_session_credentials(request_handler):
  """Load credentials from the current session."""
  session = sessions.LilCookies(request_handler, SESSION_SECRET)
  userid = session.get_secure_cookie(name='userid')
  if userid:
    return userid, StorageByKeyName(Credentials, userid, 'credentials').get()
  else:
    return None, None

def credentials_by_userid(userid):
  return StorageByKeyName(Credentials, userid, 'credentials').get()

def store_userid(request_handler, userid):
  """Store current user's ID in session."""
  session = sessions.LilCookies(request_handler, SESSION_SECRET)
  session.set_secure_cookie(name='userid', value=userid)


def create_google_service(service, version, creds=None):
  """Create a Google API service.

  Load an API service from a discovery document and authorize it with the
  provided credentials.

  Args:
    service: Service name (e.g 'mirror', 'oauth2').
    version: Service version (e.g 'v1').
    creds: Credentials used to authorize service.
  Returns:
    Authorized Google API service.
  """
  # Instantiate an Http instance
  http = httplib2.Http()

  if creds:
    # Authorize the Http instance with the passed credentials
    creds.authorize(http)

  return build(service, version, http=http)


def google_auth_required(handler_method):
  """A decorator to require that the user has authorized the Glassware."""

  def check_auth(self, *args):
    self.userid, self.credentials = load_session_credentials(self)
    self.mirror_service = create_google_service('mirror', 'v1', self.credentials)
    # TODO: Also check that credentials are still valid.
    if self.credentials:
      try:
        self.credentials.refresh(httplib2.Http())
        return handler_method(self, *args)
      except AccessTokenRefreshError:
        # Access has been revoked.
        store_userid(self, '')
        credentials_entity = Credentials.get_by_key_name(self.userid)
        if credentials_entity:
          credentials_entity.delete()
    self.redirect('/auth')
  return check_auth

def get_oauth_token_for_user(userid):
  return OAuthRequestToken.get(db.Key.from_path('OAuthRequestToken', userid))

def get_oauth_token(handler):
  return get_oauth_token_for_user(load_session_credentials(handler)[0])

def create_fitbit_oauth_service():
  #TODO: cache in memcache, like lib/oauth2client/clientsecrets.py
  try:
    fp = file('fitbit_secrets.json', 'r')
    try:
      json = simplejson.load(fp)
    finally:
      fp.close()
  except IOError:
    logging.error('Cannot find Fitbit service info')
    return None

  return OAuth1Service(
    consumer_key=json['consumer_key'],
    consumer_secret=json['consumer_secret'],
    name='fitbit',
    request_token_url='http://api.fitbit.com/oauth/request_token',
    authorize_url='http://www.fitbit.com/oauth/authorize',
    access_token_url='http://api.fitbit.com/oauth/access_token',
    base_url='http://api.fitbit.com')

#TODO: refactor
def create_fitbit_service(handler):
  token_info = get_oauth_token(handler)
  if not token_info:
    return None #No auth token in the database. need to log in to Fitbit 

  return create_fitbit_oauth_service().get_session((token_info.access_token, token_info.access_token_secret))

def create_fitbit_service_for_user(userid):
  token_info = get_oauth_token_for_user(userid)
  if not token_info:
    return None # No auth token in the database. need to log in to Fitbit 

  return create_fitbit_oauth_service().get_session((token_info.access_token, token_info.access_token_secret))

def get_preferences(userid):
  prefs = Preferences.get(db.Key.from_path('Preferences', userid))
  if not prefs:
    prefs = Preferences(key_name=userid)
    prefs.put()

  return prefs

def get_fitbit_stats(userid): 
  return FitbitStats.get(db.Key.from_path('FitbitStats', userid))

def get_fitbit_goals(userid):
  return FitbitGoals.get(db.Key.from_path('FitbitGoals', userid))

def get_fitbit_goals_reported(userid):
  return FitbitGoalsReported.get(db.Key.from_path('FitbitGoalsReported', userid))

def get_timeline_item_info(userid):
  return GlassTimelineItem.get(db.Key.from_path('GlassTimelineItem', userid))
  

