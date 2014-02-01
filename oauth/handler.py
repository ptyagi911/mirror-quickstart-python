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

__author__ = 'alainv@google.com (Alain Vongsouvanh)'


import logging
import webapp2
from urlparse import urlparse

from oauth2client.appengine import StorageByKeyName
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError

from model import Credentials 
import util
from apiclient import errors
from threading import Thread
import time

SCOPES = ('https://www.googleapis.com/auth/glass.timeline '
          'https://www.googleapis.com/auth/glass.location '
          'https://www.googleapis.com/auth/userinfo.profile')


class OAuthBaseRequestHandler(webapp2.RequestHandler):
  """Base request handler for OAuth 2.0 flow."""

  def create_oauth_flow(self):
    """Create OAuth2.0 flow controller."""
    flow = flow_from_clientsecrets('client_secrets.json', scope=SCOPES)
    # Dynamically set the redirect_uri based on the request URL. This is
    # extremely convenient for debugging to an alternative host without manually
    # setting the redirect URI.
    pr = urlparse(self.request.url)
    flow.redirect_uri = '%s://%s/oauth2callback' % (pr.scheme, pr.netloc)
    return flow


class OAuthCodeRequestHandler(OAuthBaseRequestHandler):
  """Request handler for OAuth 2.0 auth request."""

  def get(self):
    flow = self.create_oauth_flow()
    flow.params['approval_prompt'] = 'force'
    # Create the redirect URI by performing step 1 of the OAuth 2.0 web server
    # flow.
    uri = flow.step1_get_authorize_url()
    # Perform the redirect.
    self.redirect(str(uri))


class OAuthCodeExchangeHandler(OAuthBaseRequestHandler):
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

    users_service = util.create_service('oauth2', 'v2', creds)
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

  def _insert_timeline_item(self, service, text, notification_level=None):
    """Insert a new timeline item in the user's glass.
    
    Args:
    service: Authorized Mirror service.
    text: timeline item's text.
    content_type: Optional attachment's content type (supported content types
                  are 'image/*', 'video/*' and 'audio/*').
    attachment: Optional attachment as data string.
    notification_level: Optional notification level, supported values are None
                        and 'AUDIO_ONLY'.

    Returns:
    Inserted timeline item on success, None otherwise.
    """
    timeline_item = {'text': text}

    if notification_level:
      timeline_item['notification'] = {'level': notification_level}
  
    try:
      return service.timeline().insert(body=timeline_item).execute()
    except errors.HttpError, error:
      print 'An error occurred: %s' % error
        
  def _perform_post_auth_tasks(self, userid, creds):
    """Perform common post authorization tasks.

    Subscribes the service to notifications for the user and add one sharing
    contact.

    Args:
      userid: ID of the current user.
      creds: Credentials for the current user.
    """
    mirror_service = util.create_service('mirror', 'v1', creds)
    hostname = util.get_full_url(self, '')

    # Only do the post auth tasks when deployed.
    if hostname.startswith('https://'):
      # Insert a subscription.
      subscription_body = {
          'collection': 'timeline',
          # TODO: hash the userToken.
          'userToken': userid,
          'callbackUrl': util.get_full_url(self, '/notify')
      }
      mirror_service.subscriptions().insert(body=subscription_body).execute()

      # Insert a sharing contact.
      contact_body = {
          'id': 'python-quick-start',
          'displayName': 'Python Quick Start',
          'imageUrls': [util.get_full_url(self, '/static/images/python.png')],
          'acceptCommands': [{ 'type': 'TAKE_A_NOTE' }]
      }
      mirror_service.contacts().insert(body=contact_body).execute()
    else:
      logging.info('Post auth tasks are not supported on staging.')

    # Insert welcome message.
    timeline_item_body = {
        'text': 'Welcome to the Python Quick Start',
        'notification': {
            'level': 'DEFAULT'
        }
    }
    #mirror_service.timeline().insert(body=timeline_item_body).execute()
    timestamp = int(time.time())
    text = 'I have Created Priyanka' + str(timestamp)
    #self._insert_timeline_item(mirror_service, text, 'DEFAULT')
    
    #print 'Listing Priyanka items\n'
    #print self.retrieve_all_timeline_tems(mirror_service)
    #dcb3184c-5ec2-401e-9cd8-cc01d6640729
    
#   t = Thread(target=self.update_quote, args=(mirror_service, 24*60*60,))
#   t.start()  
#     
# def update_quote(self, service, delay):
#   while True:
#     item_id = 'be63e6f9-b24d-4804-8c24-e185f37ba9fb';
#     timestamp = int(time.time())
#     text = 'I have Updated Priyanka' + timestamp
#     self.update_timeline_item(service, item_id, text, 'DEFAULT');
#     time.sleep(delay)

 
  def update_timeline_item(self, service, item_id, new_text, 
                           new_notification_level=None):
    try:
      # First retrieve the timeline item from the API.
      timeline_item = service.timeline().get(id=item_id).execute()
      # Update the timeline item's metadata.
      timeline_item['text'] = new_text
      if new_notification_level:
        timeline_item['notification'] = {'level': new_notification_level}
      elif 'notification' in timeline_item:
        timeline_item.pop('notification')
      return service.timeline().update(id=item_id, body=timeline_item).execute()
    except errors.HttpError, error:
      print 'An error occurred: %s' % error
    
    return None
      
  def retrieve_all_timeline_tems(self, service):
    """Retrieve all timeline items for the current user.

    Args:
    service: Authorized Mirror service.

    Returns:
    Collection of timeline items on success, None otherwise.
    """
    result = []
    request = service.timeline().list()
    while request:
      try:
        timeline_items = request.execute()
        items = timeline_items.get('items', [])
        if items:
          result.extend(timeline_items.get('items', []))
          request = service.timeline().list_next(request, timeline_items)
        else:
          # No more items to retrieve.
          break
      except errors.HttpError, error:
          print 'An error occurred: %s' % error
          break
      return result

OAUTH_ROUTES = [
    ('/auth', OAuthCodeRequestHandler),
    ('/oauth2callback', OAuthCodeExchangeHandler)
]
