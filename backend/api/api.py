import traceback
from allauth.socialaccount.models import SocialAccount
from api.schemas import CreateMessageRequest, CreateRoomRequest, ErrorResponse, RejectProposalInnovation, SuccessResponse, CreateInnovationReq, EnterNegotiationRomReq, AcceptedProposalInnovation
from api.schemas import SaveReq, UserReq, SearchInnovationReq, ImgInnovationReq, ProposalInnovationReq, SearchroposalInnovationReq, SearchMensagensRelatedReq
from api.models import NegotiationMessage, NegotiationRoom, User, Innovation, InnovationImage, ProposalInnovation
from ninja.security import django_auth, HttpBearer
from django.contrib.auth import logout
from datetime import datetime, timedelta
import time
from ninja import NinjaAPI
from typing import Any
import requests
import pytz
import base64
import os
from django.core.files.base import ContentFile
from django.conf import settings
import jwt
from django.http import HttpResponse, Http404, JsonResponse, HttpRequest
from django.db import transaction
from django.shortcuts import get_object_or_404
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

api = NinjaAPI()

class AuthBearer(HttpBearer):
    def authenticate(self, request, token):
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return None
        except jwt.DecodeError:
            return None
        try:
            user = User.objects.get(id=payload["id"])
        except User.DoesNotExist:   
            return None
        return user
     
@api.get("/check-auth", auth=AuthBearer())
def check_auth(request):
    user = User.objects.get(id=request.auth.id) 
    return {"data": {"id": user.id}}

@api.get("/logout", response={200: SuccessResponse, 401: ErrorResponse, 404: ErrorResponse, 500: ErrorResponse})
def custom_logout(request):
    logout(request)
    return 200, {"message": "Logout feito com sucesso!"}

@api.post("/full-profile", response={200: dict, 404: dict, 401: dict})
def register(request, payload: SaveReq):

    if not payload.first_name:
        return 404, {"message": "O Primeiro nome é obrigatório para identificação do usuário no sistema!"}
    if not payload.last_name:
        return 404, {"message": "O Sobrenome é obrigatório para completar seu perfil corretamente!"}
    if not payload.categories:
        return 404, {"message": "A Categoria é obrigatória para personalizar sua experiência e conectá-lo com inovações relevantes!"}
    if not payload.data_nasc:
        return 404, {"message": "A Data de Nascimento é obrigatória para verificação de idade e conformidade com os termos de serviço!"}
    if not payload.profile_picture:
        return 404, {"message": "A Imagem de Perfil é obrigatória para que outros usuários possam identificá-lo visualmente na plataforma!"}


    logging.info(payload)
    try:
        profile_picture = None
        profile_picture_url = None

        if (
            payload.profile_picture and 
            isinstance(payload.profile_picture, str)
        ):
            if payload.profile_picture.startswith("data:image"):
                format, imgstr = payload.profile_picture.split(';base64,')
                ext = format.split('/')[-1]

                filename = f"profile_{payload.email.replace('@', '_').replace('.', '_')}_{int(time.time())}.{ext}"

                media_dir = settings.MEDIA_ROOT
                profile_pics_dir = os.path.join(media_dir, "profile_pictures")
                
                os.makedirs(profile_pics_dir, exist_ok=True)

                file_path = os.path.join(profile_pics_dir, filename)
                decoded_data = base64.b64decode(imgstr)

                with open(file_path, 'wb') as f:
                    f.write(decoded_data)

                if os.path.exists(file_path):
                    profile_picture = os.path.join("profile_pictures", filename)
                else:
                    return 500, {"message": "Falha ao salvar a imagem."}
            else:
                profile_picture_url = payload.profile_picture

        if not User.objects.filter(email=payload.email).exists():
            account = User(
                first_name=payload.first_name,
                last_name=payload.last_name,
                email=payload.email,
                data_nasc=payload.data_nasc,
                categories=payload.categories
            )
            
            if profile_picture:
                account.profile_picture = profile_picture
            elif profile_picture_url:
                account.profile_picture_url = profile_picture_url
                
            account.save()
            
            token = jwt.encode(
                {
                    'id': account.id,
                    'exp': datetime.utcnow() + timedelta(days=7), 
                    'iat': datetime.utcnow()
                },
                settings.SECRET_KEY,
                algorithm="HS256"
            )
            
            return 200, {
                "message": "Usuário registrado com sucesso!",
                "token": token,
                "user_id": account.id
            }
            
        else:
            account = User.objects.filter(email=payload.email).first()
            account.first_name = payload.first_name
            account.last_name = payload.last_name
            account.data_nasc = payload.data_nasc
            account.categories = payload.categories

            if profile_picture:
                account.profile_picture_url = None
                account.profile_picture = profile_picture
            elif profile_picture_url:
                if account.profile_picture:
                    account.profile_picture = None
                account.profile_picture_url = profile_picture_url

            account.save()
            return 200, {"message": "Perfil atualizado com sucesso!"}

    except Exception as e:
        traceback.print_exc()
        return 500, {"message": f"Erro ao processar o perfil: {str(e)}"}
    
@api.get("/obter-perfil-social-usuario", auth=django_auth, response={200: Any, 404: ErrorResponse})
def obter_perfil_social_usuario(request):

    if not request.user.is_authenticated:
        return 404, {"message": "Usuário não autenticado"}

    dados_usuario = {
        "user_id": request.user.id,
        "username": request.user.username,
        "email": request.user.email,
        "provedores": {}
    }

    contas_sociais = SocialAccount.objects.filter(user=request.user)

    for conta in contas_sociais:
        provedor = conta.provider
        dados_usuario["provedores"][provedor] = conta.extra_data

        if provedor == "linkedin-server":
            try:
                token_obj = conta.socialtoken_set.first()

                if not token_obj:
                    return 404, {"message": "Token não encontrado"}

                token_acesso = token_obj.token

                if hasattr(token_obj, "expires_at") and token_obj.expires_at < datetime.now(pytz.UTC):
                    dados_usuario["provedores"][provedor]["erro"] = "Token expirado"
                    continue

                headers = {
                    "Authorization": f"Bearer {token_acesso}",
                    "Content-Type": "application/json"
                }

                def buscar_dados_linkedin(url):
                    try:
                        resposta = requests.get(url, headers=headers)
                        if resposta.status_code == 200:
                            return resposta.json()
                        else:
                         
                            return 404, {"message": "Erro ao obter dados do LinkedIn"}

                    except requests.exceptions.RequestException:
                        return 404, {"message": "Erro na requisição ao LinkedIn"}

                dados_linkedin = buscar_dados_linkedin("https://api.linkedin.com/v2/userinfo")

                if isinstance(dados_linkedin, tuple) and dados_linkedin[0] == 404:
                    return dados_linkedin

                dados_usuario["provedores"][provedor]["perfil_linkedin"] = dados_linkedin

                if "picture" in dados_linkedin:
                    dados_usuario["provedores"][provedor]["url_imagem_perfil"] = dados_linkedin["picture"]

            except Exception:
                return 404, {"message": "Erro inesperado no processamento"}

    return 200, dados_usuario

@api.get('/get-image', auth=AuthBearer(), response={200: dict, 404: dict})
def get_user_image(request):
    try:
        user = request.auth
        # user = User.objects.get(id=1)      
    except User.DoesNotExist:
        return 404, {'message': 'Conta nao encontrada'}
        
    if user.profile_picture:
        image_url = f"{settings.MEDIA_URL}{user.profile_picture}"
        return 200, {"image_url": image_url}
    elif user.profile_picture_url:
        return 200, {"image_url": user.profile_picture_url}
    return 404, {"message": "Image not found"}



@api.get('/get-perfil', auth=AuthBearer(), response={200: dict, 404: dict})
def get_user_perfil(request):
    
    try:
        user = request.auth
        # user = User.objects.get(id=1)  
    except User.DoesNotExist:
        return 404, {'message': 'Conta nao encontrada'}
        
    data = {
        'id': user.id,
        'first_name':user.first_name if user.first_name else '-',
        'last_name': user.last_name if user.last_name else '-',
        'email': user.email if user.email else '-',
        'profile_picture': str(user.profile_picture) if user.profile_picture else '',
        'profile_picture_url': user.profile_picture_url if user.profile_picture_url else '',
        'data_nasc': user.data_nasc if user.data_nasc else '-',
        'categories': user.categories if user.categories else '-'
    }
    
    return 200, {'data': data}

@api.post('/post-create-innovation', auth=AuthBearer(), response={200: dict, 404: dict, 500: dict})
def post_create_innovation(request: HttpRequest):
    
    try:
        user = request.auth
        # user = User.objects.get(id=1)  
    except User.DoesNotExist:
        return 404, {"message": "Conta não encontrada"} 
    
    data = request.POST

    payload = CreateInnovationReq(
        partners=data.get('partners'),
        nome=data.get('nome'),
        descricao=data.get('descricao'),
        investimento_minimo=data.get('investimento_minimo'),
        porcentagem_cedida=data.get('porcentagem_cedida'),
        categorias=data.get('categorias'),
    )
        
    if payload.investimento_minimo < 0:
        return 404, {'message':'Valor indevido'}
    elif not payload.categorias:
        return 404, {'message':'Informe categorias'}
    elif not payload.porcentagem_cedida:
        return 404, {'message':'Informe porcentagem cedida'}
    elif not payload.investimento_minimo:
        return 404, {'message':'Informe investimento_minimo'}
    elif not payload.descricao:
        return 404, {'message':'Informe descricao'}
    elif not payload.nome:
        return 404, {'message':'Informe nome'}
    
    try:
        with transaction.atomic():
            innovation = Innovation(
                owner=user,
                nome=payload.nome,
                descricao=payload.descricao,
                investimento_minimo=payload.investimento_minimo,
                porcentagem_cedida=payload.porcentagem_cedida,
                categorias=payload.categorias.split(',') if payload.categorias else [],
            )
            innovation.save()

            images = []
            
            if not request.FILES.getlist('imagens'):
                return 404, {'message':'Anexe no minimo 1 img'}

            for image_file in request.FILES.getlist('imagens'):
                images.append(
                    InnovationImage(
                        owner=user,
                        innovation=innovation,
                        imagem=image_file
                    )
                )
            InnovationImage.objects.bulk_create(images)

    except Exception as e:
        return 500, {"message": str(e)}

    return 200, { "message": "Inovação criada com sucesso!"}


@api.get('/get-innovation', auth=AuthBearer(), response={200: dict, 404: dict})
def get_innovation(request):

    try:
        user = request.auth
        # user = User.objects.get(id=1)   
    except User.DoesNotExist:
        return 404, {'message': 'Conta não encontrada'}

    data = []
    
    # Obtenha o domínio base da requisição
    base_url = f"{request.scheme}://{request.get_host()}"
    
    try:
        inv = Innovation.objects.exclude(owner=user)
        
        if not inv.exists():
            return 404, {'message': 'Nenhuma inovação encontrada'}
        
        for x in inv:
            imagens = []

            list_imagem_url = x.get_all_images()
            for imagem_url in list_imagem_url:
                # Construa a URL completa para media
                if imagem_url.startswith('/media/'):
                    imagens.append(f"{base_url}{imagem_url}")
                else:
                    imagens.append(imagem_url)
                
            data.append({
                    'id': x.id,
                    'owner_id': x.owner.id,
                    'owner': x.owner.first_name,
                    'nome': x.nome,
                    'descricao': x.descricao,
                    'investimento_minimo': x.investimento_minimo,
                    'porcentagem_cedida': x.porcentagem_cedida,
                    'categorias': x.categorias,
                    'imagens': imagens,
            })

    except Exception as e:
        return 404, {'message': str(e)}

    return 200, {'data': data}

@api.post('/post-search-innovation-categories',  auth=AuthBearer(), response={200: dict, 404: dict})
def search_innovation(request, payload : SearchInnovationReq):
    try:
        user = request.auth
        # user = User.objects.get(id=1)   
    except User.DoesNotExist:
        return 404, {'message': 'Conta não encontrada'}

    data = []

    print(payload.search)
    
    try:
        inv = Innovation.objects.filter(categorias=payload.search)
        for x in inv:
            data.append({
                'id': x.id,
                'owner': x.owner.first_name if x.owner else '-',
                'partners': list(map(lambda p: {'id': p.id, 'nome': p.first_name}, x.partners.all())),
                'nome': x.nome if x.nome else '-',
                'descricao': x.descricao if x.descricao else '-',
                'investimento_minimo': x.investimento_minimo if x.investimento_minimo else '-',
                'porcentagem_cedida': x.porcentagem_cedida if x.porcentagem_cedida else '-',
                'categorias': x.categorias if x.categorias else '-',
                'imagem': x.imagem.url if x.imagem else '-',
            })

    except Exception as e:
        return 404, {'message': str(e)}

    return 200, {'data': data}

@api.post('/post-search-innovation',  auth=AuthBearer(), response={200: dict, 404: dict})
def search_innovation(request, payload : SearchInnovationReq):
    try:
        user = request.auth
        # user = User.objects.get(id=1)   
    except User.DoesNotExist:
        return 404, {'message': 'Conta não encontrada'}

    data = []

    
    try:
        inv = Innovation.objects.filter(id=payload.id).exclude(owner=user)
        for x in inv:
            data.append({
                'id': x.id,
                'owner': x.owner.first_name if x.owner else '-',
                'partners': list(map(lambda p: {'id': p.id, 'nome': p.first_name}, x.partners.all())),
                'nome': x.nome if x.nome else '-',
                'descricao': x.descricao if x.descricao else '-',
                'investimento_minimo': x.investimento_minimo if x.investimento_minimo else '-',
                'porcentagem_cedida': x.porcentagem_cedida if x.porcentagem_cedida else '-',
                'categorias': x.categorias if x.categorias else '-',
            })

    except Exception as e:
        logging.warning(str(e))
        return 404, {'message': str(e)}

    return 200, {'data': data}

# testes

@api.post("/create-room", auth=AuthBearer(), response={200: dict, 404: dict, 403: dict})
def create_room(request, payload: CreateRoomRequest):
    
    try:
        user = request.auth
    except User.DoesNotExist:
        return 404, {'message': 'Conta não encontrada'}

    try:
        investor = User.objects.get(id=payload.investor_id)
    except User.DoesNotExist:
        return 404, {'message': 'Conta não encontrada'}

    try:
        innovation = Innovation.objects.get(id=payload.innovation_id)
    except Innovation.DoesNotExist:
        return 404, {'message': 'Inovação não encontrada'}

    room, created = NegotiationRoom.objects.get_or_create(innovation=innovation)
    room.participants.add(user, investor)
    
    return 200, {
        "room_id": str(room.idRoom),
        "status": room.status,
        "participants": [u.id for u in room.participants.all()],
        "created": created
    }

@api.post("/send-message", auth=AuthBearer(), response={200: dict, 404: dict, 403: dict})
def send_message(request, payload: CreateMessageRequest):
    
    try:
        user = request.auth
    except User.DoesNotExist:
        return 404, {'message': 'Conta não encontrada'}
    
    try:
        room = NegotiationRoom.objects.get(idRoom=payload.room_id)
    except NegotiationRoom.DoesNotExist:
        return 404, {'message': 'Sala de negociação não encontrada'}

    # Verificar se o usuário é participante da sala
    if user not in room.participants.all():
        return 403, {'message': 'Você não tem permissão para enviar mensagens nesta sala'}

    try:
        # Buscar o receiver (agora obrigatório)
        try:
            receiver = User.objects.get(id=payload.receiver)
        except User.DoesNotExist:
            return 404, {'message': 'Usuário destinatário não encontrado'}

        # Verificar se o receiver é participante da sala
        if receiver not in room.participants.all():
            return 403, {'message': 'Destinatário não é participante desta sala'}

        message = NegotiationMessage.objects.create(
            room=room,
            sender=user,
            receiver=receiver,
            content=payload.content
        )

        sender_img_url = None
        if user.profile_picture and user.profile_picture.name:
            sender_img_url = f"http://localhost:8000{user.profile_picture.url}"
        elif user.profile_picture_url:
            sender_img_url = user.profile_picture_url

        message_data = {
            "id": str(message.id),
            "content": message.content,
            "sender_id": message.sender.id,
            "sender_name": f"{message.sender.first_name} {message.sender.last_name}".strip(),
            "sender_img_url": sender_img_url,
            "receiver_id": message.receiver.id,
            "receiver_name": f"{message.receiver.first_name} {message.receiver.last_name}".strip(),
            "room_id": str(message.room.idRoom),
            "created": message.created.isoformat(),
            "is_read": message.is_read,
        }

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"negotiation_{room.idRoom}",
            {
                "type": "negotiation_message",
                "message": message_data
            }
        )
        
        logging.info(f"Mensagem salva e enviada: {message.id} - {message.content}")
        return 200, message_data
        
    except Exception as e:
        logging.exception(f"Erro ao enviar mensagem: {e}")
        return 500, {'message': f'Erro ao enviar mensagem: {str(e)}'}

@api.get('/get-negotiation-room', auth=AuthBearer(), response={200: dict, 404: dict})
def get_negotiation_room(request):
    try:
        user = request.auth
        # user = User.objects.get(id=1)   
    except User.DoesNotExist:
        return 404, {'message': 'Conta não encontrada'}

    data = []

    try:
        rooms = NegotiationRoom.objects.all().first()
        if not rooms:
            return 404, {'message': 'Nenhuma sala encontrada'}
        data.append({
            'id': str(rooms.idRoom),
            'status': rooms.status,
            'participants': [{'id': u.id} for u in rooms.participants.all()],
        })

    except Exception as e:
        return 404, {'message': str(e)}

    return 200, {'data': data}

@api.post('/post-enter-negotiation-room', auth=AuthBearer(), response={200: dict, 404: dict})
def post_enter_negotiation_room(request, payload: EnterNegotiationRomReq):
    
    try:
        user = request.auth
        # user = User.objects.get(id=1)   
    except User.DoesNotExist:
        return 404, {'message': 'Conta não encontrada'} 

    try:
        room = NegotiationRoom.objects.get(idRoom=payload.id)
        
        room_data = {
            'id': str(room.idRoom),
            'status': room.status,
            'participants': [{'id': u.id} for u in room.participants.all()],
        }

    except NegotiationRoom.DoesNotExist:
        return 404, {'message': 'Sala não encontrada'}
    except Exception as e:
        return 404, {'message': str(e)}

    return 200, {'data': room_data}


@api.get('/get-messages', auth=AuthBearer(), response={200: dict, 404: dict})
def get_messages(request):
    
    try:
        user = request.auth
        
        logging.info(user.id)
        logging.info(user.first_name)
    except User.DoesNotExist:
        return 404, {'message': 'Conta não encontrada'}
    
    
    try:
        salas = NegotiationRoom.objects.all()
        rooms = []
        for sala in salas:
            if user in sala.participants.all():
                rooms.append({
                    'id': str(sala.idRoom),
                    'status': sala.status,
                    'innovation_id': sala.innovation.id,
                    'innovation_name': sala.innovation.nome,
                    'participants': [{'id': p.id, 'name': p.first_name} for p in sala.participants.all()],
                    'created': sala.created.isoformat()
                })
            
        if not rooms:
            return 404, {'message': 'Você não participa de nenhuma sala de negociação'}
            
        room = NegotiationRoom.objects.get(idRoom=rooms[0]['id'])
        
        messages = NegotiationMessage.objects.filter(room=room)
        
        base_url = f"{request.scheme}://{request.get_host()}"
        
        message_data = []
        for message in messages:
            receiver_data = None
            if isinstance(message.receiver, User):
                receiver_data = message.receiver.id
                logging.info(receiver_data)
            else:
                receiver_data = message.receiver
            
            sender_img_path = str(message.sender.profile_picture) if message.sender.profile_picture else None
                
            sender_img_url = None
            if message.sender.profile_picture_url:
                sender_img_url = message.sender.profile_picture_url
            elif sender_img_path:
                sender_img_url = f"{base_url}/media/{sender_img_path}"
            
            message_data.append({
                'id': str(message.id),
                'sender': message.sender.first_name,
                'sender_id': message.sender.id,
                'sender_img_url': sender_img_url,
                'sender_img': sender_img_path,
                'receiver_id': receiver_data,
                "receiver_name": f"{message.receiver.first_name} {message.receiver.last_name}".strip(),
                'room_id': str(message.room.idRoom),
                'content': message.content,
                'created': message.created.isoformat(),
                'is_read': message.is_read,
            })
        
        return 200, {'rooms': rooms, 'messages': message_data}
        
    except Exception as e:
        return 404, {'message': f'Erro ao buscar mensagens: {str(e)}'}


@api.post('/post-create-proposal-innovation', auth=AuthBearer() ,response={200: dict, 404: dict})
def post_create_proposal_innovation(request, payload : ProposalInnovationReq):
    
    try:
        user = request.auth
    except User.DoesNotExist:
        return 404, {'message': 'Conta não encontrada'}
    
    logging.info(payload.__dict__) 
    
    try:
        sponsored = User.objects.get(id=payload.sponsored)
    except User.DoesNotExist:
        return 404, {'message': 'sponsored não encontrada'}
    
    try:
        innovation = Innovation.objects.get(id=payload.innovation)
    except Innovation.DoesNotExist:
        return 404, {'message': 'Inovação não encontrada'}
    
    
    logging.info(f"Sponsored: {sponsored}, Innovation: {innovation}")
    try:
        with transaction.atomic():
            ppc = ProposalInnovation(
                investor = user,
                sponsored = sponsored,
                innovation= innovation,
                descricao = payload.descricao,
                investimento_minimo = payload.investimento_minimo,
                porcentagem_cedida = payload.porcentagem_cedida
            )
            ppc.save()
            
    except Exception as e:
        return 404, {'erro': f"{e}"}
    
    
    return 200, {'message': 'Proposta criada com sucesso! Aguarde a resposta do inovador.'}


@api.get('/get-proposal-innovations', auth=AuthBearer(), response={200: dict, 404: dict})
def get_proposal_innovation(request):
    try:
        user = request.auth
    except User.DoesNotExist:
        return 404, {'message': 'Conta não encontrada'}
    
    ppi = ProposalInnovation.objects.all().order_by('-created')
    
    data = []
    for x in ppi:
        data.append({
            'id': x.id,
            'created': x.created.isoformat() if hasattr(x.created, 'isoformat') else str(x.created),
            'investor_id': x.investor.id,
            'sponsored_id': x.sponsored.id,
            'innovation_id': x.innovation.id,
            'descricao': x.descricao,
            'investimento_minimo': x.investimento_minimo,
            'porcentagem_cedida': x.porcentagem_cedida,
            'accepted': x.accepted,
            'status': x.status
        })
        
    return 200, {"message": data}


@api.post('/post-search-proposal-innovations', auth=AuthBearer(), response={200: dict, 404: dict})
def get_search_proposal_innovation(request, payload : SearchroposalInnovationReq):
    
    try:
        user = request.auth
    except User.DoesNotExist:
        return 404, {'message': 'Conta não encontrada'}
    
    ppi = ProposalInnovation.objects.filter(id=payload.id)
    
    data = []
    for x in ppi:
        data.append({
            'created': x.created.isoformat() if hasattr(x.created, 'isoformat') else str(x.created),
            'investor_id': x.investor.id,
            'sponsored_id': x.sponsored.id,
            'innovation_id': x.innovation.id,
            'descricao': x.descricao,
            'investimento_minimo': x.investimento_minimo,
            'porcentagem_cedida': x.porcentagem_cedida,
            'accepted': x.accepted,
            'status': x.status
        })
        
    return 200 ,{ "message": data}

@api.get('/get-user-proposals-innovations', auth=AuthBearer(), response={200: dict, 404: dict})
def get_search_proposal_innovation(request):
    
    try:
        user = request.auth
    except User.DoesNotExist:
        
        return 404, {'message': 'Conta não encontrada'}
    
    ppi = ProposalInnovation.objects.filter(sponsored=user, accepted=False, status='pending').order_by("-created")
    
    if not ppi.exists():
        return 404, {'message': 'Nenhuma proposta encontrada para este usuário'}
        
    data = []
    for x in ppi:
        profile_picture = None
        if x.investor.profile_picture:
            profile_picture = str(x.investor.profile_picture)
            
        data.append({
            'id': x.id,
            'created': x.created.isoformat() if hasattr(x.created, 'isoformat') else str(x.created),
            'investor_id': x.investor.id,
            'investor_nome': x.investor.first_name,
            'investor_profile_picture': profile_picture,
            'investor_profile_picture_url': x.investor.profile_picture_url,
            'sponsored_id': x.sponsored.id,
            'innovation_id': x.innovation.id,
            'innovation_nome': x.innovation.nome,
            'innovation_categorias': x.innovation.categorias,
            'descricao': x.descricao,
            'investimento_minimo': x.investimento_minimo,
            'porcentagem_cedida': x.porcentagem_cedida,
            'accepted': x.accepted,
            'status': x.status
        })
        
    return 200 ,{ "message": data}



@api.get('/get-all-rooms', auth=AuthBearer(), response={200: dict, 404: dict})
def get_all_rooms(request):
    try:
        user = request.auth
        
        logging.info(user.id)
        logging.info(user.first_name)
    except User.DoesNotExist:
        return 404, {'message': 'Conta não encontrada'}
    
    
    try:
        salas = NegotiationRoom.objects.filter(participants=user)
        rooms = []
        for sala in salas:
            rooms.append({
                'id': str(sala.idRoom),
                'status': sala.status,
                'innovation_id': sala.innovation.id,
                'innovation_name': sala.innovation.nome,
                'participants': [{'id': p.id, 'name': p.first_name} for p in sala.participants.all()],
                'created': sala.created.isoformat()
            })
            
        if not rooms:
            return 404, {'message': 'Você não participa de nenhuma sala de negociação'}
            
        return 200, {'data': rooms}
    except Exception as e:
        return 404, {'message': f'Erro ao buscar salas: {str(e)}'}
    
    
@api.post('/post-search-mensagens-related', auth=AuthBearer(), response={200: dict, 404: dict})
def post_search_mensagens_related(request, payload : SearchMensagensRelatedReq):
    try:
        user = request.auth
        
    except User.DoesNotExist:
        return 404, {'message': 'Conta não encontrada'}
    
    try:
        
        try:
            room = NegotiationRoom.objects.get(idRoom=payload.id)
        except NegotiationRoom.DoesNotExist:
            return 404, {'message': 'Sala de negociação não encontrada'}
        
        if user not in room.participants.all():
            return 403, {'message': 'Você não tem permissão para acessar essa sala'}
        
        messages = NegotiationMessage.objects.filter(room=room)
        
        base_url = f"{request.scheme}://{request.get_host()}"
        
        message_data = []
        for message in messages:
            receiver_data = None
            if isinstance(message.receiver, User):
                receiver_data = message.receiver.id
            else:
                receiver_data = message.receiver
                
            sender_img_path = str(message.sender.profile_picture) if message.sender.profile_picture else None
                
            sender_img_url = None
            if message.sender.profile_picture_url:
                sender_img_url = message.sender.profile_picture_url
            elif sender_img_path:
                sender_img_url = f"{base_url}/media/{sender_img_path}"
            
            message_data.append({
                'id': str(message.id),
                'sender': message.sender.first_name,
                'sender_id': message.sender.id,
                'sender_img_url': sender_img_url,
                'sender_img': sender_img_path,
                'receiver_id': receiver_data,
                "receiver_name": f"{message.receiver.first_name} {message.receiver.last_name}".strip(),
                'room_id': str(message.room.idRoom),
                'content': message.content,
                'created': message.created.isoformat(),
                'is_read': message.is_read,
            })
        
        return 200, {'messages': message_data}
        
    except Exception as e:
        return 404, {'message': f'Erro ao buscar mensagens: {str(e)}'}


@api.post('/post-accept-proposal-innovation',auth=AuthBearer(),response={200: dict, 404: dict, 403: dict})
def post_accept_proposal_innovation(request, payload: AcceptedProposalInnovation):
    try:
        user = request.auth
    except User.DoesNotExist:
        return 404, {'message': 'Conta não encontrada'}
    
    try:
        proposal = ProposalInnovation.objects.get(id=payload.id)
    except ProposalInnovation.DoesNotExist:
        return 404, {'message': 'Proposta não encontrada'}
    
    if proposal.sponsored.id != user.id:
         return 403, {'message': 'Você não tem permissão para aceitar esta proposta'}
    
    proposal.accepted = True
    proposal.status = 'accepted'
    proposal.save()
    
    proposal_data = {
        'id': proposal.id,
        'created': proposal.created.isoformat(),
        'investor': {
            'id': proposal.investor.id,
            'name': proposal.investor.first_name
        },
        'sponsored': {
            'id': proposal.sponsored.id,
            'name': proposal.sponsored.first_name
        },
        'innovation': {
            'id': proposal.innovation.id,
            'name': proposal.innovation.nome
        },
        'descricao': proposal.descricao,
        'investimento_minimo': proposal.investimento_minimo,
        'porcentagem_cedida': proposal.porcentagem_cedida,
        'accepted': proposal.accepted,
        'status': proposal.status
    }
    
    
    
    return 200, {'message': 'Proposta aceita com sucesso!', 'proposal': proposal_data}


@api.post('/post-reject-proposal-innovation',auth=AuthBearer(),response={200: dict, 404: dict, 403: dict})
def post_reject_proposal_innovation(request, payload: RejectProposalInnovation):
    try:
        user = request.auth
    except User.DoesNotExist:
        return 404, {'message': 'Conta não encontrada'}
    
    try:
        proposal = ProposalInnovation.objects.get(id=payload.id)
    except ProposalInnovation.DoesNotExist:
        return 404, {'message': 'Proposta não encontrada'}
    
    if proposal.sponsored.id != user.id:
         return 403, {'message': 'Você não tem permissão para rejeitar esta proposta'}
    
    proposal.accepted = False
    proposal.status = 'rejected'
    proposal.save()
    
    proposal_data = {
        'id': proposal.id,
        'created': proposal.created.isoformat(),
        'investor': {
            'id': proposal.investor.id,
            'name': proposal.investor.first_name
        },
        'sponsored': {
            'id': proposal.sponsored.id,
            'name': proposal.sponsored.first_name
        },
        'innovation': {
            'id': proposal.innovation.id,
            'name': proposal.innovation.nome
        },
        'descricao': proposal.descricao,
        'investimento_minimo': proposal.investimento_minimo,
        'porcentagem_cedida': proposal.porcentagem_cedida,
        'accepted': proposal.accepted,
        'status': proposal.status
    }
    
    return 200, {'message': 'Proposta rejeitada com sucesso!', 'proposal': proposal_data}