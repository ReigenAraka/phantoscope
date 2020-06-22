# Copyright (C) 2019-2020 Zilliz. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance
# with the License. You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under the License
# is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
# or implied. See the License for the specific language governing permissions and limitations under the License.


import json
import logging
from models.application import Application as DB
from models.application import insert_application, search_application, del_application, update_application
from models.mapping import search_by_application, search_from_mapping, del_mapping
from common.error import NotExistError
from common.error import RequestError
from common.error import ArgsCheckError
from common.error import ExistError
from storage.storage import S3Ins, MilvusIns
from storage.storage import MongoIns
from application.mapping import new_mapping_ins
from application.utils import fields_check
from models.fields import insert_fields
from models.fields import Fields as FieldsDB


logger = logging.getLogger(__name__)


class Application():
    def __init__(self, name, fields, buckets):
        self._application_name = name
        self._fields = fields
        self._buckets = buckets

    @property
    def name(self):
        return self._application_name

    @property
    def fields(self):
        return self._fields

    @fields.setter
    def fields(self, fields):
        self._fields = fields

    @property
    def buckets(self):
        return self._buckets

    @buckets.setter
    def buckets(self, buckets):
        self._buckets = buckets

    def save(self):
        fields = json.dumps(self._fields)
        app = DB(name=self._application_name, fields=fields, s3_buckets=self._buckets)
        try:
            # Record created resource
            #TODO create s3 bucket if bucket not exist
            S3Ins.new_s3_buckets(self.buckets.split(","))
            #TODO create milvus collections
            insert_application(app)
            logger.info("create new application %s", self.name)
        except Exception as e:
            logger.error(e)
            #TODO collection created resource
            raise e
        return self


def all_applications():
    res = []
    try:
        apps = search_application()
        for x in apps:
            fields = json.loads(x.Application.fields)
            app = Application(name=x.Application.name, fields=fields, buckets=x.Application.s3_buckets)
            res.append(app)
        logger.info("get all application")
        return res
    except Exception as e:
        logger.error(e)
        raise e


def application_detail(name):
    try:
        x = search_application(name)
        if not x:
            raise NotExistError(f"application {name} not exist", "")
        fields = json.loads(x.fields)
        app = Application(name=x.name, fields=fields, buckets=x.s3_buckets)
        return app
    except Exception as e:
        logger.error(e)
        raise e


def new_application(app_name, fields, s3_buckets):
    ok, message = fields_check(fields)
    if not ok:
        raise ArgsCheckError(message, "")
    try:
        # check application exist
        if search_application(app_name):
            raise ExistError(f"application <{app_name}> had exist", "")
        # insert fields to metadata
        fieldsdb = []
        for name, field in fields.items():
            fieldsdb.append(FieldsDB(name=name, type=field.get('type'),
                                     value=field.get('value'), app=app_name))
        ids = insert_fields(fieldsdb)
        # create a application entity collection
        MongoIns.new_mongo_collection(app_name+"_entity")
        # insert application to metadata
        app = Application(name=app_name, fields=",".join([str(x) for x in ids]), buckets=s3_buckets)
        app.save()
        return app
    except Exception as e:
        raise e

def delete_application(name):
    try:
        if len(entities_list(name, 100, 0)):
            raise RequestError("There still have entity in this application", "")
        x = del_application(name)
        if not x:
            raise NotExistError("application %s not exist" % name, "")
        x = x[0]
        fields = json.loads(x.fields)
        app = Application(name=x.name, fields=fields, buckets=x.s3_buckets)
        S3Ins.del_s3_buckets(x.s3_buckets.split(","))
        logger.info("delete application %s", name)
        return app
    except Exception as e:
        logger.error(e)
        raise e


# def patch_application(name, fields, s3_buckets):
#    try:
#        app_model = DB(name=name, fields=json.dumps(fields), s3_buckets=s3_buckets)
#        x = update_application(name, app_model)
#        if not x:
#            raise NotExistError(f"application {name} not exist", "")
#        app = Application(name=x.name, fields=fields, buckets=s3_buckets)
#        logger.info("change appication %s config", name)
#        return app
#    except Exception as e:
#        logger.error(e)
#        return e


def entities_list(name, num, page):
    res = []
    try:
        for i in search_by_application(name, num, num*page):
            res.append(new_mapping_ins(id=i.id, app_name=i.app_name,
                                       image_url=i.image_url,
                                       fields=i.fields))
        logger.info("get application %s entity list", name)
        return res
    except Exception as e:
        logger.error(e)
        raise e


def delete_entity(app_name, entity_name):
    try:
        entity = search_from_mapping(entity_name)
        if not entity:
            raise NotExistError("Entity %s not exist" % entity_name, "NotExistError")
        MilvusIns.del_vectors(app_name, [int(entity_name)])
        bucket_name = entity.image_url.split("/")[-2]
        object_name = entity.image_url.split("/")[-1]
        S3Ins.del_object(bucket_name, object_name)
        del_mapping(entity_name)
        logger.info("delete entity %s in application %s", entity_name, app_name)
        return new_mapping_ins(
            id=entity.id, app_name=entity.app_name, image_url=entity.image_url,
            fields=entity.fields)
    except Exception as e:
        logger.error(e)
        raise e
