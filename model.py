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

"""Datastore models for M-Distance Project"""

__author__ = 'bird@codeminders.com (Alexander Sova)'


from google.appengine.ext import db

from oauth2client.appengine import CredentialsProperty


class Credentials(db.Model):
  """Datastore entity for storing OAuth2.0 credentials.

  The CredentialsProperty is provided by the Google API Python Client, and is
  used by the Storage classes to store OAuth 2.0 credentials in the data store.
  """
  credentials = CredentialsProperty()

class OAuthRequestToken(db.Model):
  """Datastore entity for storing OAuth1 Request Token for Fitbit."""
  request_token = db.StringProperty()
  request_token_secret = db.StringProperty()
  verifier = db.StringProperty()
  access_token = db.StringProperty()
  access_token_secret = db.StringProperty()
  created = db.DateTimeProperty(auto_now_add=True)

class Preferences(db.Model):
  """Datastore entity for storing user preferences."""
  hourly_updates = db.BooleanProperty(default=True)
  goal_updates = db.BooleanProperty(default=True)
  battery_level = db.BooleanProperty(default=True)

class FitbitGoals(db.Model):
  """Datastore entity for storing daily Fitbit goals."""
  steps = db.IntegerProperty(default=10000)
  floors = db.IntegerProperty(default=10)
  distance = db.FloatProperty(default=8.05) #in km
  caloriesOut = db.IntegerProperty(default=2500)
  activeMinutes = db.IntegerProperty(default=30)

class FitbitGoalsReported(db.Model):
  """Datastore entity for storing daily Fitbit goals."""
  steps = db.BooleanProperty(default=False)
  floors = db.BooleanProperty(default=False)
  distance = db.BooleanProperty(default=False)
  caloriesOut = db.BooleanProperty(default=False)
  activeMinutes = db.BooleanProperty(default=False)

class FitbitStats(db.Model):
  """Datastore entity for storing latest Fitbit activity statistics."""
  steps = db.IntegerProperty(default=0, indexed=True)
  floors = db.IntegerProperty(default=0)
  distance = db.FloatProperty(default=0.0) #in km
  caloriesOut = db.IntegerProperty(default=0)
  activeMinutes = db.IntegerProperty(default=0)
  reported = db.BooleanProperty(default=False, indexed=True)
  last_modifieed = db.DateTimeProperty(auto_now=True)

class GlassTimelineItem(db.Model):
  """Datastore entity for info about last card inserted to Glass."""
  item_id = db.StringProperty()
