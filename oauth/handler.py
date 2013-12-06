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

"""OAuth 2.0 handlers."""

__author__ = 'bird@codeminders.com (Alexander Sova)'

import logging
import webapp2
from urlparse import urlparse

from oauth2client.appengine import StorageByKeyName
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError

from model import Credentials
from model import OAuthRequestToken
import util

from rauth.service import OAuth1Service

from fitbit.client import FitbitAPI


GOOGLE_SCOPES = ('https://www.googleapis.com/auth/glass.timeline '
          'https://www.googleapis.com/auth/userinfo.profile')

class GoogleOAuthBaseRequestHandler(webapp2.RequestHandler):
  """Base request handler for OAuth 2.0 flow."""

  def create_oauth_flow(self):
    """Create OAuth2.0 flow controller."""
    flow = flow_from_clientsecrets('client_secrets.json', scope=GOOGLE_SCOPES)
    # Dynamically set the redirect_uri based on the request URL. This is
    # extremely convenient for debugging to an alternative host without manually
    # setting the redirect URI.
    pr = urlparse(self.request.url)
    flow.redirect_uri = '%s://%s/oauth2callback' % (pr.scheme, pr.netloc)
    return flow


class GoogleOAuthCodeRequestHandler(GoogleOAuthBaseRequestHandler):
  """Request handler for OAuth 2.0 auth request."""

  def get(self):
    flow = self.create_oauth_flow()
    flow.params['approval_prompt'] = 'force'
    # Create the redirect URI by performing step 1 of the OAuth 2.0 web server
    # flow.
    uri = flow.step1_get_authorize_url()
    # Perform the redirect.
    self.redirect(str(uri))
    

class GoogleOAuthCodeExchangeHandler(GoogleOAuthBaseRequestHandler):
  """Request handler for OAuth 2.0 code exchange."""

  def get(self):
    """Handle code exchange."""
    code = self.request.get('code')
    if not code:
      # TODO: Display error.
      return None
    oauth_flow = self.create_oauth_flow()

    # Perform the exchange of the code. If there is a failure with exchanging
    # the code, return None.
    try:
      creds = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
      # TODO: Display error.
      return None

    #TODO: check if it is Google response
    users_service = util.create_google_service('oauth2', 'v2', creds)
    # TODO: Check for errors.
    user = users_service.userinfo().get().execute()

    userid = user.get('id')

    # Store the credentials in the data store using the userid as the key.
    # TODO: Hash the userid the same way the userToken is.
    StorageByKeyName(Credentials, userid, 'credentials').put(creds)
    logging.info('Successfully stored credentials for user: %s', userid)
    util.store_userid(self, userid)

    self._perform_post_auth_tasks(userid, creds)
    self.redirect('/')

  def _perform_post_auth_tasks(self, userid, creds):
    """Perform commong post authorization tasks.

    Subscribes the service to notifications for the user and add one sharing
    contact.

    Args:
      userid: ID of the current user.
      creds: Credentials for the current user.
    """
    mirror_service = util.create_google_service('mirror', 'v1', creds)
    hostname = util.get_full_url(self, '')


#Fitbit Authorization endpoints
class FitbitOAuthCodeRequestHandler(webapp2.RequestHandler):
  """Request handler for OAuth 1 auth request."""

  def get(self):
    fitbit_oauth = util.create_fitbit_oauth_service()
    
    request_token, request_token_secret = fitbit_oauth.get_request_token()

    #store token and secret in DB
    userid = util.load_session_credentials(self)[0]

    token_info = OAuthRequestToken(key_name=userid)
    token_info.request_token=request_token
    token_info.request_token_secret=request_token_secret
    token_info.put()

    authorize_url = fitbit_oauth.get_authorize_url(request_token)

    # Perform the redirect.
    self.redirect(str(authorize_url))
    

class FitbitOAuthCodeExchangeHandler(webapp2.RequestHandler):
  """Request handler for OAuth 2.0 code exchange."""

  def get(self):
    """Handle code exchange."""
    token_info = util.get_oauth_token(self)

    if not token_info:
      logging.error('No OAuth token found in the storage')
      # TODO: Display error.
      return None

    oauth_verifier = self.request.get('oauth_verifier')
    if not oauth_verifier:
      logging.error('No OAuth verifier in the URL')
      # TODO: Display error.
      return None

    oauth_token = self.request.get('oauth_token')
    if not oauth_token or token_info.request_token != oauth_token:
      logging.error('Invalid OAuth token %s %s', oauth_token, token_info.request_token)
      # TODO: Display error.
      return None

    # get acceess token and store it in the database
    token_info.verifier = oauth_verifier
    fitbit_oauth = util.create_fitbit_oauth_service()
    access_token, access_token_secret = fitbit_oauth.get_access_token(token_info.request_token,  
                                      token_info.request_token_secret,
                                      data={'oauth_verifier': token_info.verifier},
                                      header_auth=True)

    token_info.access_token  = access_token
    token_info.access_token_secret = access_token_secret
    token_info.put()

    userid = util.load_session_credentials(self)[0]
    self._perform_post_auth_tasks(userid, token_info)
    #TODO: should we clean up all old subscriptions and add new one here?
    self.redirect('/')
  
  def _perform_post_auth_tasks(self, userid, token_info):
    FitbitAPI(userid).create_subscription()

OAUTH_ROUTES = [
    ('/auth', GoogleOAuthCodeRequestHandler),
    ('/oauth2callback', GoogleOAuthCodeExchangeHandler),
    ('/fitbitauth', FitbitOAuthCodeRequestHandler),
    ('/fitbitoauth2callback', FitbitOAuthCodeExchangeHandler)

]
