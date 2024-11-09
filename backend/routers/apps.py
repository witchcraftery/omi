import json
import os
import random
from typing import List

from fastapi import APIRouter, Depends, Form, UploadFile, File, HTTPException, Header

from database.apps import private_app_id_exists_db, public_app_id_exists_db, add_public_app, add_private_app, \
    get_app_by_id_db, update_private_app, update_public_app, delete_private_app, delete_public_app, \
    change_app_approval_status
from database.notifications import get_token_only
from database.redis_db import set_plugin_review, delete_generic_cache
from utils.apps import get_apps_data_from_db
from utils.notifications import send_notification
from utils.other import endpoints as auth
from models.app import App
from utils.other.storage import upload_plugin_logo, delete_plugin_logo

router = APIRouter()


@router.get('/v1/apps', tags=['v3'], response_model=List[App])
def get_apps(uid: str = Depends(auth.get_current_user_uid), include_reviews: bool = True):
    return get_apps_data_from_db(uid, include_reviews=include_reviews)


@router.get('/v1/approved-apps', tags=['v3'], response_model=App)
def get_approved_apps(uid: str = Depends(auth.get_current_user_uid)):
    return get_apps_data_from_db(uid, include_reviews=False)


@router.post('/v1/apps', tags=['v1'])
def submit_app(app_data: str = Form(...), file: UploadFile = File(...), uid=Depends(auth.get_current_user_uid)):
    data = json.loads(app_data)
    data['approved'] = False
    data['status'] = 'under-review'
    data['name'] = data['name'].strip()
    data['id'] = data['name'].replace(' ', '-').lower()
    data['uid'] = uid
    data['id'] = data['id'].replace(',', '-')
    data['id'] = data['id'].replace("'", '')
    if 'private' in data and data['private']:
        data['id'] = data['id'] + '-private'
        if private_app_id_exists_db(data['id'], uid):
            data['id'] = data['id'] + '-' + ''.join([str(random.randint(0, 9)) for _ in range(5)])
    else:
        if public_app_id_exists_db(data['id']):
            data['id'] = data['id'] + '-' + ''.join([str(random.randint(0, 9)) for _ in range(5)])
    if external_integration := data.get('external_integration'):
        # check if setup_instructions_file_path is a single url or a just a string of text
        if external_integration.get('setup_instructions_file_path'):
            external_integration['setup_instructions_file_path'] = external_integration[
                'setup_instructions_file_path'].strip()
            if external_integration['setup_instructions_file_path'].startswith('http'):
                external_integration['is_instructions_url'] = True
            else:
                external_integration['is_instructions_url'] = False
    os.makedirs(f'_temp/plugins', exist_ok=True)
    file_path = f"_temp/plugins/{file.filename}"
    with open(file_path, 'wb') as f:
        f.write(file.file.read())
    imgUrl = upload_plugin_logo(file_path, data['id'])
    data['image'] = imgUrl
    if data.get('private', True):
        print("Adding private app")
        add_private_app(data, data['uid'])
    else:
        add_public_app(data)
    return {'status': 'ok'}


@router.patch('/v1/apps/{app_id}', tags=['v1'])
def update_app(app_id: str, app_data: str = Form(...), file: UploadFile = File(None),
               uid=Depends(auth.get_current_user_uid)):
    data = json.loads(app_data)
    plugin = get_app_by_id_db(app_id, uid)
    if not plugin:
        raise HTTPException(status_code=404, detail='Plugin not found')
    if plugin['uid'] != uid:
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    if file:
        delete_plugin_logo(plugin['image'])
        os.makedirs(f'_temp/plugins', exist_ok=True)
        file_path = f"_temp/plugins/{file.filename}"
        with open(file_path, 'wb') as f:
            f.write(file.file.read())
        imgUrl = upload_plugin_logo(file_path, app_id)
        data['image'] = imgUrl
    if data.get('private', True):
        update_private_app(data, uid)
    else:
        update_public_app(data)
    return {'status': 'ok'}


@router.delete('/v1/apps/{plugin_id}', tags=['v1'])
def delete_app(app_id: str, uid: str = Depends(auth.get_current_user_uid)):
    plugin = get_app_by_id_db(app_id, uid)
    if not plugin:
        raise HTTPException(status_code=404, detail='Plugin not found')
    if plugin['uid'] != uid:
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    if plugin['private']:
        delete_private_app(app_id, uid)
    else:
        delete_public_app(app_id)
        if plugin['approved']:
            delete_generic_cache('get_public_approved_apps_data')
    return {'status': 'ok'}


@router.post('/v1/apps/{plugin_id}/approve', tags=['v1'])
def approve_app(app_id: str, uid: str, secret_key: str = Header(...)):
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    change_app_approval_status(app_id, True)
    plugin = get_app_by_id_db(app_id, uid)
    token = get_token_only(uid)
    if token:
        send_notification(token, 'App Approved 🎉',
                          f'Your app {plugin["name"]} has been approved and is now available for everyone to use 🥳')
    return {'status': 'ok'}


@router.post('/v1/plugins/{plugin_id}/reject', tags=['v1'])
def reject_app(app_id: str, uid: str, secret_key: str = Header(...)):
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    change_app_approval_status(app_id, False)
    plugin = get_app_by_id_db(app_id, uid)
    token = get_token_only(uid)
    if token:
        # TODO: Add reason for rejection in payload and also redirect to the plugin page
        send_notification(token, 'App Rejected 😔',
                          f'Your app {plugin["name"]} has been rejected. Please make the necessary changes and resubmit for approval.')
    return {'status': 'ok'}


@router.post('/v1/apps/review', tags=['v1'])
def review_app(app_id: str, data: dict, uid: str = Depends(auth.get_current_user_uid)):
    if 'score' not in data:
        raise HTTPException(status_code=422, detail='Score is required')

    plugin = get_app_by_id_db(app_id, uid)
    if not plugin:
        raise HTTPException(status_code=404, detail='Plugin not found')

    score = data['score']
    review = data.get('review', '')
    set_plugin_review(app_id, uid, score, review)
    return {'status': 'ok'}
