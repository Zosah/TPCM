import requests
from datetime import datetime
import time
import json
import os
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 从环境变量获取配置参数
WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')  # 如果环境变量未设置，默认为空字符串
if not WEBHOOK_URL:
    raise ValueError("请设置环境变量 WEBHOOK_URL")

POLL_INTERVAL = 10 * 60  # 轮询间隔（秒）

class AnnouncementSource(ABC):
    """公告来源的抽象基类"""
    @abstractmethod
    def get_announcements(self):
        """获取公告列表"""
        pass

    @abstractmethod
    def format_notification(self, item):
        """格式化通知消息"""
        pass

class WeixinPaySource(AnnouncementSource):
    """微信支付公告来源"""
    def __init__(self):
        self.base_url = "https://pay.weixin.qq.com/index.php/public/cms/get_contents"

    def get_announcements(self):
        params = {
            'id': '6200',
            'cmstype': '1',
            'url': 'https://pay.weixin.qq.com/public/cms/content_list?lang=zh&id=6200',
            'states': '2',
            'publishtimeend': '1738575930',
            'expiretimebeg': '1738575930',
            'field': 'contentId,contentTitle,contentPublishTime',
            'g_ty': 'ajax'
        }
        
        items = []
        # 获取普通公告
        params['pagenum'] = '1'
        params['propertyexclude'] = '1'
        params['ordertype'] = '4'
        response1 = requests.get(self.base_url, params=params, proxies={'http': None, 'https': None})
        
        # 获取置顶公告
        params.pop('pagenum', None)
        params.pop('propertyexclude', None)
        params['propertyinclude'] = '1'
        response2 = requests.get(self.base_url, params=params, proxies={'http': None, 'https': None})
        
        if response1.status_code == 200:
            data1 = response1.json()
            if data1.get('errorcode') == 0:
                items.extend(data1['data']['contentlist'])
                
        if response2.status_code == 200:
            data2 = response2.json()
            if data2.get('errorcode') == 0:
                items.extend(data2['data']['contentlist'])
        
        return items

    def format_notification(self, item):
        publish_time = datetime.fromtimestamp(item['contentPublishTime'])
        return {
            "title": item['contentTitle'],
            "date": publish_time.strftime('%Y-%m-%d'),
            "time": publish_time.strftime('%H:%M:%S'),
            "url": f"https://pay.weixin.qq.com/index.php/public/cms/content_detail?id={item['contentId']}",
            "source": "微信支付"
        }

class TencentCloudSource(AnnouncementSource):
    """腾讯云公告来源"""
    def __init__(self):
        self.url = "https://cloud.tencent.com/announce"

    def get_announcements(self):
        try:
            response = requests.get(self.url, proxies={'http': None, 'https': None})
            if response.status_code != 200:
                return []

            soup = BeautifulSoup(response.text, 'html.parser')
            
            announcements = []
            # 查找所有公告项
            for item in soup.select('.msg-list-bd .msg-list-item'):
                try:
                    link = item.select_one('.msg-list-con a')
                    time_span = item.select_one('.msg-list-aside span')
                    
                    if link and time_span:
                        announcements.append({
                            'title': link.text.strip(),
                            'announceId': link['href'].split('/')[-1],
                            'beginTime': time_span.text.strip()
                        })
                except Exception as e:
                    print(f"解析公告项时出错: {str(e)}")
                    continue
            
            return announcements
            
        except Exception as e:
            print(f"获取腾讯云公告失败: {str(e)}")
            return []

    def format_notification(self, item):
        date_time = item['beginTime'].split()
        return {
            "title": item['title'],
            "date": date_time[0],
            "time": date_time[1] if len(date_time) > 1 else "",
            "url": f"https://cloud.tencent.com/announce/detail/{item['announceId']}",
            "source": "腾讯云"
        }

class YeepaySource(AnnouncementSource):
    """易宝支付公告来源"""
    def __init__(self):
        self.url = "https://www.yeepay.com/all-notices"

    def get_announcements(self):
        try:
            response = requests.get(self.url, proxies={'http': None, 'https': None})
            if response.status_code != 200:
                return []

            soup = BeautifulSoup(response.text, 'html.parser')
            announcements = []
            
            # 查找所有公告项
            for tr in soup.select('.ant-table-tbody tr'):
                try:
                    link = tr.select_one('a')
                    time_td = tr.select_one('.ant-table-row-cell-break-word')
                    
                    if link and time_td:
                        announcements.append({
                            'title': link.text.strip(),
                            'noticeId': link['href'].split('/')[-1],
                            'pubTime': time_td.text.strip()
                        })
                except Exception as e:
                    print(f"解析易宝公告项时出错: {str(e)}")
                    continue
            
            return announcements
            
        except Exception as e:
            print(f"获取易宝支付公告失败: {str(e)}")
            return []

    def format_notification(self, item):
        date_time = item['pubTime'].split()
        return {
            "title": item['title'],
            "date": date_time[0],
            "time": date_time[1] if len(date_time) > 1 else "",
            "url": f"https://www.yeepay.com/notice-detail/{item['noticeId']}",
            "source": "易宝支付"
        }

class AnnouncementMonitor:
    def __init__(self):
        self.sources = []
        self.last_items = set()  # 存储已经发送过的公告
        self.debug_time = None   # 用于调试的时间
        self.is_first_run = True # 标记是否是第一次运行

    def add_source(self, source):
        """添加公告来源"""
        self.sources.append(source)

    def set_debug_time(self, debug_time_str):
        """设置调试时间"""
        self.debug_time = datetime.strptime(debug_time_str, "%Y-%m-%d")

    def send_notification(self, item):
        """发送企业微信通知"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = {
            "msgtype": "markdown",
            "markdown": {
                "content": (
                    f"### 📢 「{item['source']}」新公告\n\n" +
                    f"**标题**：{item['title']}\n\n" +
                    f"**时间**：{item['date']}" + 
                    (f" {item['time']}" if 'time' in item else "") + "\n\n" +
                    f"**链接**：[点击查看详情]({item['url']})\n\n" +
                    f"**巡检**：{current_time}"
                )
            }
        }
        
        response = requests.post(WEBHOOK_URL, json=message, proxies={'http': None, 'https': None})
        if response.status_code != 200:
            print(f"发送通知失败: {response.text}")

    def check_updates(self):
        """检查更新"""
        try:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for source in self.sources:
                items = source.get_announcements()
                # 输出轮询时间和来源
                print(f'[{current_time}] 正在检查 {source.__class__.__name__.replace("Source", "")} 公告，获取到 {len(items)} 条')
                
                for raw_item in items:
                    item = source.format_notification(raw_item)
                    item_date = datetime.strptime(item['date'], "%Y-%m-%d")
                    item_key = f"{item['source']}_{item['title']}_{item['date']}"
                    
                    # 如果在调试模式下，检查日期是否晚于调试时间
                    if self.debug_time and item_date.date() >= self.debug_time.date():
                        print(f'[{current_time}] DEBUG-检测到新公告：{item_key}')
                        if not self.is_first_run and item_key not in self.last_items:
                            self.send_notification(item)
                            self.last_items.add(item_key)
                        elif self.is_first_run:
                            self.last_items.add(item_key)
                    # 正常模式下，检查是否为新公告
                    elif not self.debug_time and item_key not in self.last_items:
                        print(f'[{current_time}] 检测到新公告：{item_key}')
                        if not self.is_first_run:
                            self.send_notification(item)
                        self.last_items.add(item_key)
            
            if self.is_first_run:
                print(f"首次运行，已收集 {len(self.last_items)} 条现有公告")
                self.is_first_run = False
                
        except Exception as e:
            print(f"检查更新时发生错误: {str(e)}")

    def run(self):
        """运行监控"""
        # 发送启动通知
        startup_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # startup_message = {
        #     "msgtype": "markdown",
        #     "markdown": {
        #         "content": (
        #             f"### 🚀 公告监控服务已启动\n\n" +
        #             f"**启动时间**：{startup_time}\n\n" +
        #             f"**监控对象**：\n" +
        #             "\n".join([f"- {source.__class__.__name__.replace('Source', '')}" 
        #                       for source in self.sources]) + "\n\n" +
        #             f"**巡检间隔**：{POLL_INTERVAL//60} 分钟"
        #         )
        #     }
        # }
        
        # requests.post(WEBHOOK_URL, json=startup_message, proxies={'http': None, 'https': None})
        print(f"监控服务已启动，当前时间: {startup_time}")
        
        while True:
            self.check_updates()
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    monitor = AnnouncementMonitor()
    monitor.add_source(WeixinPaySource())
    monitor.add_source(TencentCloudSource())
    monitor.add_source(YeepaySource())
    # monitor.set_debug_time("2025-01-15")
    monitor.run()
