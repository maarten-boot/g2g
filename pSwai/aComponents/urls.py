from appAutoGui.xauto import url_gen_all

from aComponents import views
from aComponents.autoGui import AUTO_GUI

urlpatterns = []
urlpatterns += url_gen_all(
    AUTO_GUI,
    __package__,
    views.index,
    views.form,
)
