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

"""Request Handler for /fitbit endpoints."""

__author__ = 'info@codeminders.com'


import logging
import webapp2

from google.appengine.api import urlfetch

from model import Credentials
import util



class FitbitSubscriptionHandler(webapp2.RequestHandler):
  """Request Handler for the signout endpoint."""

  def post(self):
    """Delete the user's credentials from the datastore."""
    logging.info('POST: SUBSCRIPTION UPDATE from Fitbit')

  def get(self):
    """Delete the user's credentials from the datastore."""
    logging.info('POST: SUBSCRIPTION UPDATE from Fitbit')


FITBIT_ROUTES = [
    ('/fitbitsub', FitbitSubscriptionHandler)
]
