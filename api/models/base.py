from django.db import models


class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # django 的元数据选项 表示这是一个用于模板的抽象基类 不会创建数据表 只能由于继承
    # https://docs.djangoproject.com/zh-hans/5.1/topics/db/models/#abstract-base-classes
    class Meta:
        abstract = True

    # 重写delete方法
    # def delete(self, using=None, keep_parents=False):
    #     self.is_deleted = True
    #     self.deleted_at = timezone.now()
    #     self.save()
