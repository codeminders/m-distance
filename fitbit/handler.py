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

#TODO: move it somehwere
def create_subscription(handler):

  userid = util.load_session_credentials(handler)[0]
  logging.info('Creating Fitbit subscription for user %s' % userid)

  # check if subscription exists
  fitbit_service = util.create_fitbit_service(handler)
  r = fitbit_service.get('http://api.fitbit.com/1/user/-/apiSubscriptions.json', header_auth=True)
  if r.status_code == 200:
    subs = r.json()['apiSubscriptions']


    #TODO: for testing only. deleting subscription 
    # if len(subs) == 1: 
    #   logging.info('List of fitbit subscriptions %s', str(subs[0]))
    #   r = fitbit_service.delete('http://api.fitbit.com/1/user/-/apiSubscriptions/%s.json' % userid, header_auth=True)
    # else:
    #   logging.info('HUH??? %s', len(subs))

    #TODO: delete subscription if subs[0]['subscriptionId'] != userid:
    # creating new fitbit subscription

    if len(subs) == 0:
      r = fitbit_service.post('http://api.fitbit.com/1/user/-/apiSubscriptions/%s.json' % userid, data={}, header_auth=True)
      logging.info('Adding new subscription. The code: %s' % r.status_code)
    else:
      logging.info('Found subscription. Subscription id: %s Subscriber id: %s', subs[0]['subscriptionId'], subs[0]['subscriberId'])
  
  else:
    logging.error('Cannot get list of fitbit subscriptions for user %s', userid)


class FitbitSubscriptionHandler(webapp2.RequestHandler):
  """Request Handler for the signout endpoint."""

  def post(self):
    logging.info('POST: SUBSCRIPTION UPDATE from Fitbit %s', self.request.body)
    self.response.set_status(204)

  def get(self):
    logging.info('GET: SUBSCRIPTION UPDATE from Fitbit')
    self.response.set_status(204)



FITBIT_ROUTES = [
    ('/fitbitsub', FitbitSubscriptionHandler)
]
